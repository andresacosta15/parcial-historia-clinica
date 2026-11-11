import urllib.request
import urllib.error
import json
import os

FHIR_BASE = os.getenv("FHIR_BASE_URL", "http://localhost:8080/fhir")

async def send_bundle(bundle: dict, sede: str = "sincelejo"):
    url = FHIR_BASE
    body = json.dumps(bundle).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/fhir+json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"HTTP {e.code}: {error_body}")
