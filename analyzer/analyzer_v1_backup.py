"""
analyzer.py — active-probe clinical-integrity analyzer (the research core).

Loop: replay a synthetic probe cohort against the CANARY version of the clinical
service -> read back what it wrote to FHIR -> score clinical-semantic integrity
-> publish the score as a Prometheus gauge. Argo Rollouts' clinical-gate
AnalysisTemplate queries that gauge to promote or roll back.

Runs in BOTH arms; only the gate differs. In the baseline arm nobody gates on
this score, which lets you SHOW that a clinically-broken release the infra gate
admitted had a low clinical-integrity score all along.
"""
import logging
import os
import time
import uuid

import requests
from prometheus_client import Counter, Gauge, start_http_server

import signals as sg

CANARY_BASE = os.environ.get("CANARY_BASE", "http://clinical-service-canary:8000")
FHIR_BASE = os.environ.get("FHIR_BASE", "http://fhir:8080/fhir")
PROBE_INTERVAL = int(os.environ.get("PROBE_INTERVAL", "15"))
COHORT_SIZE = int(os.environ.get("COHORT_SIZE", "20"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9110"))
EXPECTED_VALUE = 72  # known ground-truth heart rate we send every probe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("analyzer")

integrity_score = Gauge(
    "clinical_integrity_score",
    "Fraction of probe observations that are clinically intact (0..1)")
probes_total = Counter(
    "clinical_probes_total", "Probe observations attempted")
corrupted_total = Counter(
    "clinical_corrupted_total",
    "Probe observations found clinically corrupted", ["signal"])

FHIR_HEADERS = {"Accept": "application/fhir+json"}


def probe_once(session):
    """Run one probe cohort against the canary; return integrity score in [0,1] or None."""
    intact, total = 0, 0
    for _ in range(COHORT_SIZE):
        # 1) admit a patient + 2) post a known-good observation, both via the CANARY
        try:
            adm = session.post(
                f"{CANARY_BASE}/admit",
                json={"family": "Probe", "given": "P" + uuid.uuid4().hex[:6],
                      "gender": "unknown"}, timeout=20)
            if adm.status_code != 200:
                continue  # hard failure -> infra gate's job, not ours
            patient_id = adm.json()["patient_id"]

            obs_resp = session.post(
                f"{CANARY_BASE}/observation",
                json={"patient_id": patient_id, "kind": "heart_rate",
                      "value": EXPECTED_VALUE}, timeout=20)
            if obs_resp.status_code != 200:
                continue
            obs_id = obs_resp.json()["observation_id"]
        except (requests.RequestException, KeyError):
            continue

        total += 1

        # 3) read back what the canary actually persisted, then score it
        try:
            got = session.get(f"{FHIR_BASE}/Observation/{obs_id}",
                              headers=FHIR_HEADERS, timeout=15)
            if got.status_code != 200:
                corrupted_total.labels(signal="unreadable").inc()
                continue
            obs = got.json()
        except requests.RequestException:
            continue

        ok, failures = sg.evaluate_observation(
            obs, patient_id, EXPECTED_VALUE, FHIR_BASE, session)
        if ok:
            intact += 1
        else:
            for signal in failures:
                corrupted_total.labels(signal=signal).inc()
            log.info("corrupt observation %s: %s", obs_id, failures)

    probes_total.inc(total)
    if total == 0:
        return None
    return intact / total


def main():
    start_http_server(METRICS_PORT)
    log.info("analyzer up on :%d, probing canary=%s fhir=%s",
             METRICS_PORT, CANARY_BASE, FHIR_BASE)
    session = requests.Session()
    while True:
        try:
            score = probe_once(session)
            if score is not None:
                integrity_score.set(score)
                log.info("clinical_integrity_score=%.3f", score)
            else:
                log.info("canary unreachable / no successful probes this cycle")
        except Exception as e:  # never let the loop die
            log.exception("probe cycle failed: %s", e)
        time.sleep(PROBE_INTERVAL)


if __name__ == "__main__":
    main()
