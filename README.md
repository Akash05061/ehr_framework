# Cloud-Native EHR Continuous-Delivery Framework

Research vehicle for **clinical-integrity-gated progressive delivery**: a rollout
controller that gates canary promotion on clinical-semantic integrity signals
(FHIR conformance under load, cross-resource referential integrity, terminology
binding, HL7->FHIR mapping fidelity) — defects invisible to both infrastructure
metrics and static pre-prod validation.

**Contribution metric:** *clinical blast radius* — synthetic patients whose data
is corrupted before automated rollback.

---

## Repo layout
```
app/              HAPI FHIR server (docker-compose)   <- the EHR backend (scaffolding)
synthea/          Synthetic cohort generation          <- your zero-PHI test data
scripts/          Data loading + smoke tests
k8s/              Kubernetes manifests (added Day 3-4)
```

## Day 1-2: stand up the backend + data

### 1. Start the FHIR server
```bash
cd app
docker compose up -d
# wait ~30-60s for HAPI to finish starting
```

### 2. Generate synthetic patients (needs Java 11+)
```bash
cd ../synthea
chmod +x generate.sh
./generate.sh 1000 42        # 1000 patients, fixed seed 42 (reproducible)
```

### 3. Load the data
```bash
cd ../scripts
pip install requests
python load_bundles.py --dir ../synthea/output/fhir --base http://localhost:8080/fhir
```

### 4. Verify
```bash
chmod +x smoke_test.sh
./smoke_test.sh
```
Expect a non-zero Patient count and Observation count. **That's Day 1-2 done.**

---

## Next
- Day 3-4: containerize the thin clinical service, deploy to Kubernetes
  (k3s-on-EC2 recommended over EKS for speed), install Argo Rollouts, get a
  baseline canary gated on infra metrics only.
- Day 5-8: the clinical integrity analyzer (the paper).
