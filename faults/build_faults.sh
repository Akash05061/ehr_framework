#!/usr/bin/env bash
# build_faults.sh — build one clinical-service image per fault variant.
# Each image is the normal service with the variant's fhir_mapping.py swapped in.
# Run from repo root:  bash faults/build_faults.sh
# (k3s: images are imported into containerd; EKS: push to ECR instead.)
set -euo pipefail

SVC_DIR="app/clinical-service"
K3S="${K3S:-1}"     # set K3S=0 to skip the k3s import step

# also (re)build the clean baseline so v1 is available as an image
echo ">> building clinical-service:v1-clean"
docker build -q -t clinical-service:v1-clean "$SVC_DIR" >/dev/null
[ "$K3S" = "1" ] && docker save clinical-service:v1-clean | sudo k3s ctr images import - >/dev/null

for variant in faults/v2_*.py; do
  name=$(basename "$variant" .py | sed 's/^v2_//; s/_/-/g')   # e.g. broken-reference
  tag="clinical-service:v2-$name"
  echo ">> building $tag"
  # stage a build context: the service dir but with the variant mapping
  tmp=$(mktemp -d)
  cp "$SVC_DIR"/* "$tmp"/
  cp "$variant" "$tmp"/fhir_mapping.py
  docker build -q -t "$tag" "$tmp" >/dev/null
  rm -rf "$tmp"
  [ "$K3S" = "1" ] && docker save "$tag" | sudo k3s ctr images import - >/dev/null
done

echo
echo ">> done. Images built:"
docker images 'clinical-service' --format '   {{.Repository}}:{{.Tag}}'
