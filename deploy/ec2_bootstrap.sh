#!/usr/bin/env bash
# EC2 validation-phase bootstrap for Ubuntu 22.04+.
# Assumes you have git-cloned this repo onto the instance and are running from
# the repo root:  bash deploy/ec2_bootstrap.sh
set -euo pipefail

echo ">> Installing Docker + compose plugin..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER" || true

echo ">> Bringing up the full application..."
sudo docker compose -f deploy/docker-compose.ec2.yml up -d --build

echo ">> Waiting 60s for HAPI to finish starting..."
sleep 60

echo ">> Smoke test:"
curl -sf http://localhost:8000/health && echo "  clinical-service OK"
curl -sf http://localhost:8080/fhir/metadata > /dev/null && echo "  HAPI OK"

cat <<'NOTE'

------------------------------------------------------------
NEXT:
  1. Security group: expose 8000/8080 ONLY to your own IP, not 0.0.0.0/0.
  2. Load synthetic data (from your laptop or the instance):
       python scripts/load_bundles.py --dir synthea/output/fhir \
         --base http://<EC2_PUBLIC_IP>:8080/fhir
  3. Record baseline latency/stability numbers -> paper's "EC2 validation".
  4. Then move to the Kubernetes phase (the contribution lives there).
------------------------------------------------------------
NOTE
