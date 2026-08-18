#!/usr/bin/env python3
"""
run_experiment.py — the two-arm experiment that produces the paper's numbers.

For each fault variant, and for each gate arm (infra-gate = baseline,
clinical-gate = your contribution), it:
  1. resets the rollout to the clean v1,
  2. deploys the fault variant as the canary,
  3. watches whether the rollout is PROMOTED (fault shipped) or ABORTED (caught),
  4. measures CLINICAL BLAST RADIUS = corrupted observations written before the
     rollout ended (from the analyzer's clinical_corrupted_total counter),
  5. records detection (caught?) and time-to-detection.

Run from repo root, with the k8s cluster up and images built:
    python experiment/run_experiment.py --repeats 5

Requires: kubectl on PATH, the argo-rollouts kubectl plugin, and Prometheus
reachable via `kubectl -n monitoring port-forward svc/prometheus-server 9090:80`
running in another terminal (or set --prom to a reachable URL).

NOTE: this orchestrates real kubectl calls. Start with --repeats 1 to smoke-test
the loop before doing a full run.
"""
import argparse
import csv
import json
import subprocess
import time
import urllib.request

NS = "ehr"
ROLLOUT = "clinical-service"
CONTAINER = "clinical-service"

FAULTS = [
    ("broken-reference", "clinical-service:v2-broken-reference", True),
    ("wrong-codesystem", "clinical-service:v2-wrong-codesystem", True),
    ("bad-terminology", "clinical-service:v2-bad-terminology", True),
    ("truncated-value", "clinical-service:v2-truncated-value", True),
    ("drop-status", "clinical-service:v2-drop-status", False),  # infra-visible-ish
]
ARMS = {"baseline": "infra-gate", "treatment": "clinical-gate"}
CLEAN_IMAGE = "clinical-service:v1-clean"


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def patch_gate(template_name):
    """Point the rollout's analysis step at the chosen AnalysisTemplate."""
    steps = [
        {"setWeight": 25}, {"pause": {"duration": "30s"}},
        {"analysis": {"templates": [{"templateName": template_name}]}},
        {"setWeight": 50}, {"pause": {"duration": "30s"}}, {"setWeight": 100},
    ]
    patch = {"spec": {"strategy": {"canary": {"steps": steps}}}}
    sh(f"kubectl -n {NS} patch rollout {ROLLOUT} --type merge -p '{json.dumps(patch)}'")


def set_image(image):
    sh(f"kubectl -n {NS} set image rollout/{ROLLOUT} {CONTAINER}={image}")


def reset_to_clean():
    set_image(CLEAN_IMAGE)
    # let it fully roll out and settle
    sh(f"kubectl argo rollouts -n {NS} get rollout {ROLLOUT} > /dev/null")
    time.sleep(20)


def rollout_status():
    """Return 'Healthy', 'Degraded', 'Paused', etc."""
    r = sh(f"kubectl -n {NS} get rollout {ROLLOUT} -o jsonpath='{{.status.phase}}'")
    return r.stdout.strip().strip("'")


def prom_counter(prom, query):
    """Scalar value of a Prometheus instant query (0.0 if absent)."""
    url = f"{prom}/api/v1/query?query={urllib.parse.quote(query)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.load(resp)
        res = data["data"]["result"]
        return float(res[0]["value"][1]) if res else 0.0
    except Exception:
        return 0.0


def run_case(fault_name, image, arm, template, prom, timeout=300):
    reset_to_clean()
    before = prom_counter(prom, "sum(clinical_corrupted_total)")
    patch_gate(template)
    t0 = time.time()
    set_image(image)

    # poll until the rollout is promoted (Healthy on new rev) or aborted (Degraded)
    outcome, elapsed = "timeout", timeout
    while time.time() - t0 < timeout:
        phase = rollout_status()
        if phase == "Degraded":       # gate aborted the rollout -> caught
            outcome, elapsed = "caught", time.time() - t0
            break
        if phase == "Healthy":        # promoted -> fault shipped
            outcome, elapsed = "shipped", time.time() - t0
            break
        time.sleep(5)

    after = prom_counter(prom, "sum(clinical_corrupted_total)")
    blast_radius = max(0, int(after - before))
    return {
        "fault": fault_name, "arm": arm, "outcome": outcome,
        "caught": outcome == "caught",
        "time_to_outcome_s": round(elapsed, 1),
        "clinical_blast_radius": blast_radius,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--prom", default="http://localhost:9090",
                    help="Prometheus base URL (port-forward it)")
    ap.add_argument("--out", default="experiment/results.csv")
    args = ap.parse_args()

    rows = []
    for rep in range(1, args.repeats + 1):
        for fault_name, image, _infra_invisible in FAULTS:
            for arm, template in ARMS.items():
                print(f"[rep {rep}] {fault_name} / {arm} ...", flush=True)
                row = run_case(fault_name, image, arm, template, args.prom)
                row["repeat"] = rep
                rows.append(row)
                print(f"    -> {row['outcome']}, "
                      f"blast_radius={row['clinical_blast_radius']}", flush=True)

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "repeat", "fault", "arm", "outcome", "caught",
            "time_to_outcome_s", "clinical_blast_radius"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} rows to {args.out}")
    print("Analyze with:  python experiment/metrics.py")


if __name__ == "__main__":
    import urllib.parse  # noqa: E402
    main()
