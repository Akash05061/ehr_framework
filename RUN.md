# RUN.md — how to run the system

Two stages. Do Stage 1 first and confirm it works before touching Kubernetes.

Prerequisites: Docker, Java 11+ (for Synthea), Python 3.10+, and for Stage 2:
kubectl, Helm, and a Kubernetes cluster (k3s recommended — see Stage 2).

---

## STAGE 1 — Local app validation (docker-compose)

Goal: prove the EHR app works — FHIR backend, synthetic data, clinical service.

```bash
# 1. Start Postgres + HAPI FHIR
cd app
docker compose up -d
sleep 60                     # HAPI is slow to boot

# 2. Generate a reproducible synthetic cohort (seed 42)
cd ../synthea
chmod +x generate.sh
./generate.sh 1000 42

# 3. Load it into HAPI
cd ../scripts
pip install requests
python load_bundles.py --dir ../synthea/output/fhir --base http://localhost:8080/fhir

# 4. Verify data landed
chmod +x smoke_test.sh
./smoke_test.sh              # expect non-zero Patient + Observation counts

# 5. Run the clinical service (new terminal)
cd ../app/clinical-service
pip install -r requirements.txt
FHIR_BASE=http://localhost:8080/fhir uvicorn main:app --port 8000
```

Exercise it (another terminal):
```bash
curl -s -X POST localhost:8000/admit -H 'content-type: application/json' \
  -d '{"family":"Test","given":"Ada","gender":"female"}'
# copy the patient_id, then:
curl -s -X POST localhost:8000/observation -H 'content-type: application/json' \
  -d '{"patient_id":"PASTE_ID","kind":"heart_rate","value":72}'
curl -s localhost:8000/patients/PASTE_ID | head -c 300
```

✅ CHECKPOINT: admit returns an id, observation writes (no 502), patient round-trips.
   Also browse the HAPI tester UI at http://localhost:8080/ (doctor-style search).

Optional — EC2: same thing on an instance via `bash deploy/ec2_bootstrap.sh`
(run from the repo root). Lock the security group to your own IP.

---

## STAGE 2 — Kubernetes experiment plumbing

Goal: deploy everything to Kubernetes and confirm the analyzer's clinical-integrity
score is visible to Prometheus and the gates are installed.

### 2a. Cluster (k3s — the fast path)
```bash
curl -sfL https://get.k3s.io | sh -
mkdir -p ~/.kube && sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
kubectl get nodes                       # Ready?
```
(EKS instead: create the cluster with eksctl, and in step 2d PUSH images to ECR
and set the manifest `image:` fields to the ECR path instead of importing.)

### 2b. Add-ons: Argo Rollouts + Prometheus
```bash
# Argo Rollouts controller
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml

# kubectl plugin (to watch rollouts)
curl -LO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64
chmod +x kubectl-argo-rollouts-linux-amd64
sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts

# Prometheus (classic chart — honors prometheus.io/scrape pod annotations)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
kubectl create namespace monitoring
helm install prometheus prometheus-community/prometheus -n monitoring
```

### 2c. IMPORTANT: align the Prometheus address in the gates
Both AnalysisTemplates must point at your Prometheus service. With the classic
chart that is `http://prometheus-server.monitoring.svc:9090`. File 41 already
uses it; fix file 40:
```bash
sed -i 's#prometheus-operated.monitoring.svc:9090#prometheus-server.monitoring.svc:9090#' \
  k8s/40-analysis-infra.yaml
```

### 2d. Build images and import into k3s
```bash
docker build -t clinical-service:latest app/clinical-service
docker build -t clinical-analyzer:latest analyzer
docker save clinical-service:latest  | sudo k3s ctr images import -
docker save clinical-analyzer:latest | sudo k3s ctr images import -
```

### 2e. Deploy
```bash
kubectl apply -f k8s/                    # namespace, postgres, hapi, rollout, infra gate
kubectl apply -f k8s-research/           # analyzer + clinical gate
kubectl -n ehr get pods                  # wait until all Running
```
(HAPI in-cluster starts empty. The analyzer self-generates its probe patients,
so loading Synthea data here is OPTIONAL for the experiment.)

### 2f. Verify the plumbing (the part most likely to need a tweak)
The analyzer only produces a score while it can reach canary pods. For a quick
plumbing check, temporarily point it at the STABLE service so it always has a
target:
```bash
kubectl -n ehr set env deployment/clinical-analyzer CANARY_BASE=http://clinical-service-stable:8000
kubectl -n ehr logs deploy/clinical-analyzer -f     # expect: clinical_integrity_score=1.000
```
Then confirm Prometheus sees it. Port-forward and query:
```bash
kubectl -n monitoring port-forward svc/prometheus-server 9090:80
# open http://localhost:9090 and run:   avg(clinical_integrity_score)
```
✅ CHECKPOINT: the query returns ~1.0. Scraping + query + metric all work.

Now revert the analyzer to probe the CANARY for real experiments:
```bash
kubectl -n ehr set env deployment/clinical-analyzer CANARY_BASE=http://clinical-service-canary:8000
```

---

## What's NOT runnable yet
Triggering a canary and watching a rollback needs a "bad" version to deploy.
Those are the fault variants (faults/ — next build). Once they exist:
```bash
# deploy a fault variant as the canary and watch the gate react
kubectl -n ehr set image rollout/clinical-service clinical-service=clinical-service-fault-broken-ref:latest
kubectl argo rollouts get rollout clinical-service -n ehr --watch
```
With the clinical-gate, that rollout auto-rolls-back; with the infra-gate, it
promotes a broken release. That contrast is the experiment.
