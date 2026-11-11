import urllib.request
import urllib.error
import json
import os

FHIR_URLS = {
    "sincelejo": os.getenv("FHIR_SINCELEJO", "http://hapi-fhir-sincelejo:8080/fhir"),
    "cartagena": os.getenv("FHIR_CARTAGENA", "http://hapi-fhir-cartagena:8080/fhir"),
    "corozal":   os.getenv("FHIR_COROZAL",   "http://hapi-fhir-corozal:8080/fhir"),
}

SEDES = list(FHIR_URLS.keys())


async def send_bundle(bundle: dict, sede: str = "sincelejo"):
    """Envía un Bundle FHIR al HAPI de la sede indicada."""
    if sede not in FHIR_URLS:
        raise ValueError(f"Sede inválida: {sede}. Use una de {SEDES}")
    url = FHIR_URLS[sede]
    body = json.dumps(bundle).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/fhir+json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"[{sede}] HTTP {e.code}: {error_body}")


async def query_sede(sede: str, path: str):
    """Consulta un path de FHIR en una sede. Devuelve None si la sede no responde."""
    if sede not in FHIR_URLS:
        return None
    url = f"{FHIR_URLS[sede]}/{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def sede_disponible(sede: str) -> bool:
    """Verifica si la sede responde consultando /metadata."""
    if sede not in FHIR_URLS:
        return False
    url = f"{FHIR_URLS[sede]}/metadata"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/fhir+json"})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False
