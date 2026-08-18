"""
analyzer.py — active-probe clinical-integrity analyzer (research core).

EKS approach: pod IPs ARE routable on real clusters, so the analyzer finds the
canary pods directly via the Kubernetes API (reading the Rollout's canary
pod-template-hash) and probes them by pod IP -- bypassing the canary Service
entirely (which Argo Rollouts controls and would otherwise route to all pods).
"""
import logging, os, time, uuid
import requests, urllib3
from prometheus_client import Counter, Gauge, start_http_server
import signals as sg
import json as _json
import threading as _threading
from http.server import BaseHTTPRequestHandler as _BH, HTTPServer as _HS

_latest_score = {"score": 1.0}

class _ScoreHandler(_BH):
    def do_GET(self):
        if self.path == "/score":
            body = _json.dumps(_latest_score).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *a):
        pass

def _serve_score(port):
    _HS(("0.0.0.0", port), _ScoreHandler).serve_forever()

urllib3.disable_warnings()

FHIR_BASE = os.environ.get("FHIR_BASE", "http://fhir:8080/fhir")
PROBE_INTERVAL = int(os.environ.get("PROBE_INTERVAL", "10"))
COHORT_SIZE = int(os.environ.get("COHORT_SIZE", "20"))
METRICS_PORT = int(os.environ.get("METRICS_PORT", "9110"))
ROLLOUT_NAME = os.environ.get("ROLLOUT_NAME", "clinical-service")
APP_LABEL = os.environ.get("APP_LABEL", "clinical-service")
SVC_PORT = int(os.environ.get("SVC_PORT", "8000"))
EXPECTED_VALUE = 72

SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
K8S_API = "https://kubernetes.default.svc"
try:
    SA_TOKEN = open(f"{SA_DIR}/token").read().strip()
    NAMESPACE = open(f"{SA_DIR}/namespace").read().strip()
    CA_CERT = f"{SA_DIR}/ca.crt"
except FileNotFoundError:
    SA_TOKEN, NAMESPACE, CA_CERT = "", "ehr", False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("analyzer")
integrity_score = Gauge("clinical_integrity_score", "intact fraction 0..1")
probes_total = Counter("clinical_probes_total", "probes attempted")
corrupted_total = Counter("clinical_corrupted_total", "corrupt probes", ["signal"])
FHIR_HEADERS = {"Accept": "application/fhir+json"}
K8S_HEADERS = {"Authorization": f"Bearer {SA_TOKEN}"}

def k8s_get(path):
    r = requests.get(K8S_API + path, headers=K8S_HEADERS, verify=CA_CERT, timeout=10)
    r.raise_for_status(); return r.json()

def canary_pod_ips():
    try:
        ro = k8s_get(f"/apis/argoproj.io/v1alpha1/namespaces/{NAMESPACE}/rollouts/{ROLLOUT_NAME}")
    except requests.RequestException as e:
        log.warning("cannot read rollout: %s", e); return []
    s = ro.get("status", {}); ch = s.get("currentPodHash", ""); sh = s.get("stableRS", "")
    if not ch or ch == sh:
        return []
    try:
        pods = k8s_get(f"/api/v1/namespaces/{NAMESPACE}/pods"
                       f"?labelSelector=app={APP_LABEL},rollouts-pod-template-hash={ch}")
    except requests.RequestException as e:
        log.warning("cannot list pods: %s", e); return []
    ips = []
    for p in pods.get("items", []):
        st = p.get("status", {})
        if st.get("phase") != "Running":
            continue
        ready = all(c.get("ready") for c in st.get("containerStatuses", [])) if st.get("containerStatuses") else False
        ip = st.get("podIP")
        if ready and ip:
            ips.append(ip)
    return ips

def probe(session, base):
    intact = total = 0
    for _ in range(COHORT_SIZE):
        try:
            a = session.post(f"{base}/admit", json={"family":"Probe","given":"P"+uuid.uuid4().hex[:6],"gender":"unknown"}, timeout=15)
            if a.status_code != 200: continue
            pid = a.json()["patient_id"]
            o = session.post(f"{base}/observation", json={"patient_id":pid,"kind":"heart_rate","value":EXPECTED_VALUE}, timeout=15)
            if o.status_code != 200: continue
            oid = o.json()["observation_id"]
        except (requests.RequestException, KeyError): continue
        total += 1
        try:
            g = session.get(f"{FHIR_BASE}/Observation/{oid}", headers=FHIR_HEADERS, timeout=15)
            if g.status_code != 200: corrupted_total.labels(signal="unreadable").inc(); continue
            obs = g.json()
        except requests.RequestException: continue
        ok, fail = sg.evaluate_observation(obs, pid, EXPECTED_VALUE, FHIR_BASE, session)
        if ok: intact += 1
        else:
            for sig in fail: corrupted_total.labels(signal=sig).inc()
            log.info("corrupt observation %s: %s", oid, fail)
    return intact, total

def main():
    start_http_server(METRICS_PORT)
    _threading.Thread(target=_serve_score, args=(9111,), daemon=True).start()
    log.info("analyzer up :%d ns=%s rollout=%s (direct canary-pod probing / EKS)", METRICS_PORT, NAMESPACE, ROLLOUT_NAME)
    session = requests.Session()
    while True:
        try:
            ips = canary_pod_ips()
            if not ips:
                log.info("no canary in progress")
            else:
                intact = total = 0
                for ip in ips:
                    i, t = probe(session, f"http://{ip}:{SVC_PORT}")
                    intact += i; total += t
                probes_total.inc(total)
                if total:
                    sc = intact/total; integrity_score.set(sc); _latest_score["score"] = sc
                    log.info("canary pods=%s clinical_integrity_score=%.3f", ips, sc)
                else:
                    log.info("canary pods=%s but no successful probes", ips)
        except Exception as e:
            log.exception("cycle failed: %s", e)
        time.sleep(PROBE_INTERVAL)

if __name__ == "__main__":
    main()
