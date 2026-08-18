#!/usr/bin/env bash
# Verify the FHIR server is alive and report how many patients loaded.
set -euo pipefail
BASE="${1:-http://localhost:8080/fhir}"

echo ">> CapabilityStatement (server alive?):"
curl -sf "$BASE/metadata" | head -c 200 && echo -e "\n   OK\n"

echo ">> Patient count:"
curl -sf "$BASE/Patient?_summary=count" \
  | grep -o '"total":[0-9]*' || echo "   (could not read count)"

echo -e "\n>> Observation count:"
curl -sf "$BASE/Observation?_summary=count" \
  | grep -o '"total":[0-9]*' || echo "   (could not read count)"
