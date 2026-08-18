#!/usr/bin/env bash
# Generate a synthetic patient cohort as FHIR R4 transaction bundles.
# Requires Java 11+.  Usage: ./generate.sh [num_patients] [seed]
set -euo pipefail

NUM_PATIENTS="${1:-1000}"
SEED="${2:-42}"
JAR="synthea-with-dependencies.jar"
JAR_URL="https://github.com/synthetichealth/synthea/releases/download/master-branch-latest/synthea-with-dependencies.jar"

cd "$(dirname "$0")"

if [ ! -f "$JAR" ]; then
  echo ">> Downloading Synthea..."
  curl -L -o "$JAR" "$JAR_URL"
fi

echo ">> Generating $NUM_PATIENTS patients (seed=$SEED)..."
# -p N patients, fixed seed for reproducibility (important for your experiment),
# FHIR R4 transaction bundles, US/Massachusetts default population.
java -jar "$JAR" \
  -p "$NUM_PATIENTS" \
  -s "$SEED" \
  --exporter.fhir.export=true \
  --exporter.fhir.transaction_bundle=true \
  --exporter.hospital.fhir.export=true \
  --exporter.practitioner.fhir.export=true

echo ">> Done. Bundles are in ./output/fhir/"
ls -1 output/fhir/ | head -n 5
echo "   (total: $(ls -1 output/fhir/ | wc -l) files)"
