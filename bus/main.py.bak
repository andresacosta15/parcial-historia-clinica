from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import hl7apy
from hl7apy.parser import parse_message
import pandas as pd
import io
import uuid
import os
import requests
from jose import jwt, JWTError
from prometheus_fastapi_instrumentator import Instrumentator

from idempotency import setup_idempotency
from audit import log_event, verify_audit
from fhir_client import send_bundle

app = FastAPI(title="HSB - Historia Clínica Distribuida")

# CORS para el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://0.0.0.0:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_idempotency(app)

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8081")
REALM = "historia-clinica"
FHIR_URL = os.getenv("FHIR_URL", "http://localhost:8080/fhir")

_jwks_cache = None


# ---------- Utilidades de normalización ----------

def _map_gender(value) -> str:
    """Mapea M/F/masculino/femenino a códigos FHIR R4 válidos."""
    if value is None or (isinstance(value, float) and value != value):
        return "unknown"
    v = str(value).strip().lower()
    mapping = {
        "m": "male", "masculino": "male", "hombre": "male",
        "f": "female", "femenino": "female", "mujer": "female",
        "o": "other", "otro": "other",
    }
    return mapping.get(v, "unknown")


def _format_date(value):
    """Normaliza fechas a YYYY-MM-DD. Acepta YYYYMMDD, YYYY-MM-DD, NaN."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    s = str(value).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


# ---------- Autenticación ----------

def get_jwks():
    global _jwks_cache
    if _jwks_cache is None:
        url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"
        resp = requests.get(url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


def validate_token(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token requerido")
    token = authorization.replace("Bearer ", "")
    try:
        jwks = get_jwks()
        unverified = jwt.get_unverified_header(token)
        key = next((k for k in jwks["keys"] if k["kid"] == unverified["kid"]), None)
        if not key:
            raise HTTPException(status_code=401, detail="Clave no encontrada")
        payload = jwt.decode(
            token, key, algorithms=[key.get("alg", "RS256")],
            options={"verify_aud": False},
        )
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token inválido: {str(e)}")


def require_roles(roles: list):
    def checker(payload: dict = Depends(validate_token)):
        user_roles = payload.get("realm_access", {}).get("roles", [])
        if not any(r in user_roles for r in roles):
            raise HTTPException(status_code=403, detail=f"Requiere uno de: {roles}")
        return payload
    return checker


class HL7Message(BaseModel):
    message: str


# ---------- Endpoints ----------

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ingest/hl7")
async def ingest_hl7(
    payload: HL7Message,
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(require_roles(["admisionista", "medico"])),
):
    message = payload.message
    try:
        msg = parse_message(message)
        msg_type = msg.MSH.MSH_9.value
        pid = msg.PID
        patient_id = pid.PID_3.PID_3_1.value
        family_name = pid.PID_5.PID_5_1.value if pid.PID_5 else "Desconocido"
        given_name = pid.PID_5.PID_5_2.value if pid.PID_5 else ""
        patient_uuid = f"urn:uuid:{uuid.uuid4()}"
        gender_raw = pid.PID_8.value if hasattr(pid, "PID_8") else None
        birth_raw = pid.PID_7.value if hasattr(pid, "PID_7") else None
        patient_resource = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.gov.co/id", "value": patient_id}],
            "name": [{"family": family_name, "given": [given_name]}],
            "gender": _map_gender(gender_raw),
        }
        birth = _format_date(birth_raw)
        if birth:
            patient_resource["birthDate"] = birth
        bundle = {
            "resourceType": "Bundle", "type": "transaction",
            "entry": [{
                "fullUrl": patient_uuid,
                "resource": patient_resource,
                "request": {"method": "POST", "url": "Patient"},
            }],
        }
        if "ADT" in msg_type and hasattr(msg, "PV1"):
            pv1 = msg.PV1
            encounter_id = pv1.PV1_19.value if pv1.PV1_19 else str(uuid.uuid4())
            bundle["entry"].append({
                "resource": {
                    "resourceType": "Encounter",
                    "identifier": [{"value": encounter_id}],
                    "status": "in-progress",
                    "subject": {"reference": patient_uuid},
                },
                "request": {"method": "POST", "url": "Encounter"},
            })
        result = await send_bundle(bundle)
        await log_event(
            usuario=user.get("preferred_username", "desconocido"),
            accion="ingest_hl7",
            recurso=f"Patient/{patient_id}",
            metadata={"msg_type": msg_type, "idempotency_key": idempotency_key},
        )
        return {"status": "procesado", "fhir_response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando HL7: {str(e)}")


@app.post("/ingest/csv")
async def ingest_csv(
    file: UploadFile = File(...),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(require_roles(["admisionista"])),
):
    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode("utf-8")))
    bundles = []
    for _, row in df.iterrows():
        patient_uuid = f"urn:uuid:{uuid.uuid4()}"
        patient_resource = {
            "resourceType": "Patient",
            "identifier": [{"value": str(row.get("documento_id", ""))}],
            "name": [{
                "family": str(row.get("apellido", "")),
                "given": [str(row.get("nombre", ""))],
            }],
            "gender": _map_gender(row.get("sexo")),
        }
        birth = _format_date(row.get("fecha_nacimiento"))
        if birth:
            patient_resource["birthDate"] = birth
        bundles.append({
            "resourceType": "Bundle", "type": "transaction",
            "entry": [{
                "fullUrl": patient_uuid,
                "resource": patient_resource,
                "request": {"method": "POST", "url": "Patient"},
            }],
        })
    results = []
    for b in bundles:
        results.append(await send_bundle(b))
    await log_event(
        usuario=user.get("preferred_username", "desconocido"),
        accion="ingest_csv",
        recurso=f"archivo:{file.filename}",
        metadata={"registros": len(bundles)},
    )
    return {"status": "procesado", "registros": len(bundles), "resultados": results}


@app.get("/audit/verify")
async def verify(user: dict = Depends(require_roles(["auditor"]))):
    report = await verify_audit()
    return {"audit_report": str(report)}


@app.get("/patients")
async def list_patients(user: dict = Depends(require_roles(["admisionista", "medico", "auditor"]))):
    try:
        resp = requests.get(f"{FHIR_URL}/Patient?_count=100",
                            headers={"Accept": "application/fhir+json"})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error consultando FHIR: {str(e)}")


@app.get("/patients/{patient_id}/bundle")
async def get_patient_bundle(patient_id: str, user: dict = Depends(validate_token)):
    roles = user.get("realm_access", {}).get("roles", [])
    if "paciente" in roles:
        if patient_id != user.get("preferred_username"):
            raise HTTPException(status_code=403, detail="Solo puedes ver tu propia historia")
    elif not any(r in roles for r in ["medico", "auditor", "admisionista"]):
        raise HTTPException(status_code=403, detail="Sin permiso")
    try:
        resp = requests.get(f"{FHIR_URL}/Patient?identifier={patient_id}",
                            headers={"Accept": "application/fhir+json"})
        resp.raise_for_status()
        bundle = resp.json()
        if bundle.get("total", 0) == 0:
            raise HTTPException(status_code=404, detail="Paciente no encontrado")
        patient_ref = bundle["entry"][0]["resource"]["id"]
        results = {"Patient": bundle}
        for resource in ["Encounter", "Observation", "Condition"]:
            r = requests.get(f"{FHIR_URL}/{resource}?patient={patient_ref}",
                             headers={"Accept": "application/fhir+json"})
            if r.status_code == 200:
                results[resource] = r.json()
        return results
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.post("/diagnostico")
async def create_diagnostico(
    patient_id: str,
    codigo_cie10: str,
    descripcion: str,
    user: dict = Depends(require_roles(["medico"])),
):
    try:
        bundle = {
            "resourceType": "Bundle", "type": "transaction",
            "entry": [{
                "resource": {
                    "resourceType": "Condition",
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{
                        "system": "http://hl7.org/fhir/sid/icd-10",
                        "code": codigo_cie10,
                        "display": descripcion,
                    }]},
                    "subject": {"reference": f"Patient?identifier={patient_id}"},
                },
                "request": {"method": "POST", "url": "Condition"},
            }],
        }
        result = await send_bundle(bundle)
        await log_event(
            usuario=user.get("preferred_username", "desconocido"),
            accion="create_diagnostico",
            recurso=f"Patient/{patient_id}",
            metadata={"cie10": codigo_cie10},
        )
        return {"status": "procesado", "fhir_response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/reporte")
async def get_reporte(user: dict = Depends(require_roles(["auditor", "medico"]))):
    try:
        stats = {}
        for resource in ["Patient", "Encounter", "Observation", "Condition"]:
            r = requests.get(f"{FHIR_URL}/{resource}?_summary=count",
                             headers={"Accept": "application/fhir+json"})
            stats[resource] = r.json().get("total", 0) if r.status_code == 200 else 0
        audit = await verify_audit()
        return {
            "tablero": stats,
            "auditoria": str(audit),
            "sedes": {"sincelejo": "disponible", "cartagena": "disponible", "corozal": "disponible"},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


Instrumentator().instrument(app).expose(app, endpoint="/metrics")
