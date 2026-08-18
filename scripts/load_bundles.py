#!/usr/bin/env python3
"""
Load Synthea FHIR R4 transaction bundles into a HAPI FHIR server.

Order matters: hospitalInformation* and practitionerInformation* bundles must be
posted first, because patient bundles reference those Organizations/Practitioners.

Usage:
    python load_bundles.py --dir ../synthea/output/fhir --base http://localhost:8080/fhir
"""
import argparse
import glob
import os
import sys
import time

import requests


def post_bundle(base, path, session):
    with open(path, "r", encoding="utf-8") as f:
        bundle = f.read()
    resp = session.post(
        base,
        data=bundle,
        headers={"Content-Type": "application/fhir+json"},
        timeout=120,
    )
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Directory of Synthea FHIR bundles")
    ap.add_argument("--base", default="http://localhost:8080/fhir", help="FHIR base URL")
    args = ap.parse_args()

    files = glob.glob(os.path.join(args.dir, "*.json"))
    if not files:
        print(f"No .json files found in {args.dir}", file=sys.stderr)
        sys.exit(1)

    # Dependency order: infrastructure bundles before patient bundles.
    infra = sorted(f for f in files if os.path.basename(f).startswith(
        ("hospitalInformation", "practitionerInformation")))
    patients = sorted(f for f in files if f not in infra)
    ordered = infra + patients

    session = requests.Session()
    ok, failed = 0, 0
    start = time.time()

    for i, path in enumerate(ordered, 1):
        try:
            resp = post_bundle(args.base, path, session)
            if resp.status_code in (200, 201):
                ok += 1
            else:
                failed += 1
                print(f"[{i}/{len(ordered)}] FAIL {resp.status_code} "
                      f"{os.path.basename(path)}: {resp.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            failed += 1
            print(f"[{i}/{len(ordered)}] ERROR {os.path.basename(path)}: {e}",
                  file=sys.stderr)

        if i % 50 == 0:
            print(f"  ...{i}/{len(ordered)} posted "
                  f"({ok} ok, {failed} failed, {time.time()-start:.0f}s)")

    print(f"\nDone: {ok} ok, {failed} failed in {time.time()-start:.0f}s")
    sys.exit(1 if failed and ok == 0 else 0)


if __name__ == "__main__":
    main()
