#!/usr/bin/env bash
# k8s_setup.sh — stand up the full experiment on a k3s cluster.
# Run from the repo root, AFTER Stage 1 works. Assumes k3s + kubectl + helm +
# docker are installed and `kubectl get nodes` shows Ready.
# (EKS users: skip the ctr-import lines, push images to ECR, and set the
#  manifest image: fields to the ECR path instead.)
set -euo pipefail

echo ">> [1/5] Argo Rollouts controller + kubectl plugin"
kubectl create namespace argo-rollouts --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argo-rollouts \
  -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
if ! command -v kubectl-argo-rollouts >/dev/null 2>&1; then
  curl -sLO https://github.com/argoproj/argo-rollouts/releases/latest/download/kubectl-argo-rollouts-linux-amd64
  chmod +x kubectl-argo-rollouts-linux-amd64
  sudo mv kubectl-argo-rollouts-linux-amd64 /usr/local/bin/kubectl-argo-rollouts
fi

echo ">> [2/5] Prometheus (classic chart, honors pod-annotation scraping)"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install prometheus prometheus-community/prometheus -n monitoring

echo ">> [3/5] Align Prometheus address in the infra gate"
sed -i 's#prometheus-operated.monitoring.svc:9090#prometheus-server.monitoring.svc:9090#' \
  k8s/40-analysis-infra.yaml || true

echo ">> [4/5] Build + import images into k3s containerd"
docker build -t clinical-service:latest app/clinical-service
docker build -t clinical-analyzer:latest analyzer
docker save clinical-service:latest  | sudo k3s ctr images import -
docker save clinical-analyzer:latest | sudo k3s ctr images import -

echo ">> [5/5] Deploy"
kubectl apply -f k8s/
kubectl apply -f k8s-research/

echo
echo ">> Done. Watch pods come up:  kubectl -n ehr get pods -w"
echo ">> Then verify plumbing per RUN.md section 2f (point analyzer at stable,"
echo "   confirm avg(clinical_integrity_score) ~ 1.0 in Prometheus)."
