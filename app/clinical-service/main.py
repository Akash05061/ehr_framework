"""
main.py — the thin clinical service.

This is the component you version and deploy. v1 vs v2 of THIS service are what
your canary compares. It fronts HAPI FHIR with a few clinical workflows and
exposes Prometheus metrics so Argo Rollouts can gate on it.

Endpoints:
  GET  /health            liveness  (always 200 if the process is up)
  GET  /ready             readiness (200 only if HAPI is reachable)
  POST /admit             create Patient + Encounter
  POST /observation       record an Observation for a patient
  GET  /patients/{id}     fetch a patient
  GET  /metrics           Prometheus (added by the instrumentator)
"""
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

import fhir_mapping as fm

FHIR_BASE = os.environ.get("FHIR_BASE", "http://localhost:8080/fhir")
FHIR_HEADERS = {"Content-Type": "application/fhir+json",
                "Accept": "application/fhir+json"}

app = FastAPI(title="EHR Clinical Service", version=fm.VERSION)

# Allow the browser demo UI (opened from file:// or localhost) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)  # exposes /metrics

# Reuse one async client for HAPI calls.
client = httpx.AsyncClient(base_url=FHIR_BASE, headers=FHIR_HEADERS, timeout=30.0)


@app.get("/health")
async def health():
    # Liveness: up = 200, regardless of clinical correctness.
    # A clinically-broken v2 STILL passes this. That's the whole research point.
    return {"status": "ok", "version": fm.VERSION}


@app.get("/ready")
async def ready():
    try:
        r = await client.get("/metadata")
        if r.status_code == 200:
            return {"status": "ready", "version": fm.VERSION}
    except httpx.HTTPError:
        pass
    raise HTTPException(status_code=503, detail="FHIR backend not reachable")


async def _create(resource: dict) -> dict:
    rtype = resource["resourceType"]
    r = await client.post(f"/{rtype}", json=resource)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502,
                            detail=f"FHIR write failed: {r.status_code} {r.text[:300]}")
    return r.json()


@app.post("/admit")
async def admit(request: Request):
    payload = await request.json()
    ok, msg = fm.validate_light(payload)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    patient = await _create(fm.build_patient(payload))
    patient_id = patient["id"]
    encounter = await _create(fm.build_encounter(patient_id, payload))
    return {"patient_id": patient_id, "encounter_id": encounter["id"],
            "version": fm.VERSION}


@app.post("/observation")
async def observation(request: Request):
    payload = await request.json()
    ok, msg = fm.validate_light(payload)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    patient_id = payload.get("patient_id")
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id required")

    obs = await _create(fm.build_observation(patient_id, payload))
    return {"observation_id": obs["id"], "version": fm.VERSION}


@app.get("/patients/{patient_id}")
async def get_patient(patient_id: str):
    r = await client.get(f"/Patient/{patient_id}")
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text[:300])
    return r.json()


@app.put("/patients/{patient_id}")
async def update_patient(patient_id: str, request: Request):
    """Update (replace) a patient's demographics — the U in CRUD."""
    payload = await request.json()
    ok, msg = fm.validate_light(payload)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    patient = fm.build_patient(payload)
    patient["id"] = patient_id                       # FHIR update needs the id in body
    r = await client.put(f"/Patient/{patient_id}", json=patient)
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=502,
                            detail=f"FHIR update failed: {r.status_code} {r.text[:300]}")
    return {"patient_id": patient_id, "version": fm.VERSION}


@app.delete("/patients/{patient_id}")
async def delete_patient(patient_id: str):
    """Delete a patient and everything referencing them (cascade) — the D in CRUD."""
    r = await client.delete(f"/Patient/{patient_id}?_cascade=delete")
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=502,
                            detail=f"FHIR delete failed: {r.status_code} {r.text[:300]}")
    return {"deleted": patient_id, "version": fm.VERSION}


@app.delete("/observation/{obs_id}")
async def delete_observation(obs_id: str):
    """Delete a single observation."""
    r = await client.delete(f"/Observation/{obs_id}")
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=502,
                            detail=f"FHIR delete failed: {r.status_code} {r.text[:300]}")
    return {"deleted": obs_id, "version": fm.VERSION}
