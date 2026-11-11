from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
from fhir_client import send_bundle, query_sede, sede_disponible, SEDES

app = FastAPI(title="HSB - Historia Clínica Distribuida")

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

_jwks_cache = None


# ---------- Utilidades de normalización ----------

def _map_gender(value) -> str:
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
    if value is None or (isinstance(value, float) and value != value):
        return None
    s = str(value).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return s
    return None


def _normalize_sede(raw) -> str:
    """Normaliza el nombre de la sede. Default: sincelejo."""
    if not raw:
        return "sincelejo"
    s = str(raw).strip().lower()
    for sede in SEDES:
        if sede in s:
            return sede
    return "sincelejo"


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
    x_sede: str = Header("sincelejo", alias="X-Sede"),
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
        sede = _normalize_sede(x_sede)
        result = await send_bundle(bundle, sede=sede)
        await log_event(
            usuario=user.get("preferred_username", "desconocido"),
            accion="ingest_hl7",
            recurso=f"Patient/{patient_id}",
            metadata={"msg_type": msg_type, "sede": sede, "idempotency_key": idempotency_key},
        )
        return {"status": "procesado", "sede": sede, "fhir_response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando HL7: {str(e)}")


@app.post("/ingest/csv")
async def ingest_csv(
    file: UploadFile = File(...),
    x_sede: str = Header("sincelejo", alias="X-Sede"),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
    user: dict = Depends(require_roles(["admisionista"])),
):
    contents = await file.read()
    df = pd.read_csv(io.StringIO(contents.decode("utf-8")))
    sede = _normalize_sede(x_sede)
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
        results.append(await send_bundle(b, sede=sede))
    await log_event(
        usuario=user.get("preferred_username", "desconocido"),
        accion="ingest_csv",
        recurso=f"archivo:{file.filename}",
        metadata={"registros": len(bundles), "sede": sede},
    )
    return {"status": "procesado", "sede": sede, "registros": len(bundles), "resultados": results}


@app.get("/audit/verify")
async def verify(user: dict = Depends(require_roles(["auditor"]))):
    report = await verify_audit()
    return {"audit_report": str(report)}


@app.get("/sedes/estado")
async def estado_sedes():
    """Devuelve el estado real de cada sede (disponible/no disponible)."""
    estados = {}
    for sede in SEDES:
        estados[sede] = "disponible" if sede_disponible(sede) else "no disponible"
    return {"sedes": estados}


@app.get("/patients")
async def list_patients(
    x_sede: str = Header(None, alias="X-Sede"),
    user: dict = Depends(require_roles(["admisionista", "medico", "auditor"])),
):
    try:
        if x_sede:
            sede = _normalize_sede(x_sede)
            result = await query_sede(sede, "Patient?_count=100")
            if result is None:
                raise HTTPException(status_code=503, detail=f"Sede {sede} no disponible")
            return result
        merged_entries = []
        no_disponibles = []
        for sede in SEDES:
            r = await query_sede(sede, "Patient?_count=100")
            if r is None:
                no_disponibles.append(sede)
                continue
            for e in r.get("entry", []):
                e["_sede"] = sede
                merged_entries.append(e)
        return {
            "resourceType": "Bundle",
            "type": "searchset",
            "total": len(merged_entries),
            "entry": merged_entries,
            "sedes_no_disponibles": no_disponibles,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/patients/{patient_id}/bundle")
async def get_patient_bundle(patient_id: str, user: dict = Depends(validate_token)):
    roles = user.get("realm_access", {}).get("roles", [])
    if "paciente" in roles:
        if patient_id != user.get("preferred_username"):
            raise HTTPException(status_code=403, detail="Solo puedes ver tu propia historia")
    elif not any(r in roles for r in ["medico", "auditor", "admisionista"]):
        raise HTTPException(status_code=403, detail="Sin permiso")

    results = {}
    sedes_consultadas = []
    sedes_no_disponibles = []

    for sede in SEDES:
        patient_bundle = await query_sede(sede, f"Patient?identifier={patient_id}")
        if patient_bundle is None:
            sedes_no_disponibles.append(sede)
            continue
        sedes_consultadas.append(sede)
        if patient_bundle.get("total", 0) > 0:
            patient_ref = patient_bundle["entry"][0]["resource"]["id"]
            sede_data = {"Patient": patient_bundle}
            for resource in ["Encounter", "Observation", "Condition"]:
                r = await query_sede(sede, f"{resource}?patient={patient_ref}")
                if r:
                    sede_data[resource] = r
            results[sede] = sede_data

    if not results and sedes_no_disponibles:
        raise HTTPException(
            status_code=503,
            detail=f"Todas las sedes no disponibles: {sedes_no_disponibles}",
        )
    if not results:
        raise HTTPException(status_code=404, detail="Paciente no encontrado en ninguna sede")

    await log_event(
        usuario=user.get("preferred_username", "desconocido"),
        accion="view_bundle",
        recurso=f"Patient/{patient_id}",
        metadata={"sedes": sedes_consultadas},
    )

    return {
        "paciente": patient_id,
        "sedes_con_datos": list(results.keys()),
        "sedes_consultadas": sedes_consultadas,
        "sedes_no_disponibles": sedes_no_disponibles,
        "datos": results,
    }


@app.post("/diagnostico")
async def create_diagnostico(
    patient_id: str,
    codigo_cie10: str,
    descripcion: str,
    x_sede: str = Header("sincelejo", alias="X-Sede"),
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
        sede = _normalize_sede(x_sede)
        result = await send_bundle(bundle, sede=sede)
        await log_event(
            usuario=user.get("preferred_username", "desconocido"),
            accion="create_diagnostico",
            recurso=f"Patient/{patient_id}",
            metadata={"cie10": codigo_cie10, "sede": sede},
        )
        return {"status": "procesado", "sede": sede, "fhir_response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/reporte")
async def get_reporte(user: dict = Depends(require_roles(["auditor", "medico"]))):
    try:
        tablero = {}
        sedes_estado = {}
        for sede in SEDES:
            sede_stats = {}
            disponible = True
            for resource in ["Patient", "Encounter", "Observation", "Condition"]:
                r = await query_sede(sede, f"{resource}?_summary=count")
                if r is None:
                    disponible = False
                    sede_stats[resource] = 0
                else:
                    sede_stats[resource] = r.get("total", 0)
            tablero[sede] = sede_stats
            sedes_estado[sede] = "disponible" if disponible else "no disponible"
        audit = await verify_audit()
        return {
            "tablero_por_sede": tablero,
            "sedes": sedes_estado,
            "auditoria": str(audit),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


Instrumentator().instrument(app).expose(app, endpoint="/metrics")
