# FILES.md — complete project manifest

Every file in this project, what it does, and its status. Start with `RUN.md`
for how to run it. Legend: ✅ built & ready · ⏳ next build (not yet here).

## Top level
- `README.md` — project overview and Day 1-2 quickstart.
- `RUN.md` — **authoritative staged runbook** (Stage 1 local → Stage 2 Kubernetes).
- `FILES.md` — this manifest.
- `.gitignore` — keeps generated Synthea data + jar out of git.
- `.github/workflows/ci.yml` — GitHub Actions: build image + Trivy scan (the DevSecOps gate).

## app/ — the EHR application (the deployed vehicle)
- `app/docker-compose.yml` — local Postgres + HAPI FHIR (Stage 1 dev backend).
- `app/clinical-service/main.py` — FastAPI clinical service; the VERSIONED, deployed component.
- `app/clinical-service/fhir_mapping.py` — **the injectable surface**; v1-clean. Fault variants edit this one file.
- `app/clinical-service/requirements.txt` — service deps.
- `app/clinical-service/Dockerfile` — container image for the service.

## synthea/ + scripts/ — data and helpers
- `synthea/generate.sh` — generate a reproducible synthetic cohort (seed 42), zero PHI.
- `scripts/load_bundles.py` — load Synthea bundles into HAPI in dependency order.
- `scripts/smoke_test.sh` — verify server up + patient/observation counts.
- `scripts/k8s_setup.sh` — one-shot Kubernetes setup for the k3s path (add-ons, images, apply).

## deploy/ — EC2 validation phase
- `deploy/docker-compose.ec2.yml` — whole app (db + HAPI + service) on one instance.
- `deploy/ec2_bootstrap.sh` — install Docker + bring the app up on fresh Ubuntu EC2.

## k8s/ — Kubernetes phase (baseline arm)
- `k8s/00-namespace.yaml` — the `ehr` namespace.
- `k8s/10-postgres.yaml` — Postgres deploy + service.
- `k8s/20-hapi.yaml` — HAPI FHIR deploy + service.
- `k8s/30-clinical-rollout.yaml` — Argo Rollout (canary) + stable/canary services.
- `k8s/40-analysis-infra.yaml` — **baseline gate**: infra metrics only (the control arm).

## k8s-research/ — Kubernetes phase (treatment arm = the contribution)
- `k8s-research/42-analyzer.yaml` — the clinical-integrity analyzer deploy + service.
- `k8s-research/41-analysis-clinical.yaml` — **clinical gate**: promotes/rolls back on integrity score.

## analyzer/ — the research core
- `analyzer/signals.py` — clinical-semantic signals (referential integrity, terminology, value fidelity, required fields).
- `analyzer/analyzer.py` — active-probe service: replays cohort at canary, scores it, exposes to Prometheus.
- `analyzer/requirements.txt` — analyzer deps.
- `analyzer/Dockerfile` — container image for the analyzer.

## ⏳ Not yet built (the remaining work)
- `faults/` — 5 fault variants (each = `fhir_mapping.py` + one line) + build script. **Next build.**
- `experiment/` — `workload.py`, `run_experiment.py`, `metrics.py`: run both arms × faults,
  measure detection rate, false-positive rate, and clinical blast radius. **Days 11-12.**

These two directories produce the paper's actual RESULTS. Everything above is the
system that makes them measurable.
