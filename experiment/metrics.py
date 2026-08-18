#!/usr/bin/env python3
"""
metrics.py — turn results.csv into the paper's headline numbers.

Computes, per arm:
  - detection rate (fraction of fault deployments caught / rolled back)
  - mean clinical blast radius (patients corrupted before the rollout ended)
  - mean time-to-outcome
and prints a per-fault breakdown plus the overall comparison. This is the table
that shows the baseline ships clinically-broken releases the treatment catches.

Run from repo root:  python experiment/metrics.py
"""
import argparse
import csv
import statistics as st
from collections import defaultdict


def load(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def summarize(rows):
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)

    print("=" * 64)
    print("OVERALL (all faults)")
    print("=" * 64)
    print(f"{'arm':<12}{'detection rate':<18}{'mean blast radius':<20}{'mean time (s)'}")
    for arm, rs in by_arm.items():
        caught = sum(1 for r in rs if r["caught"] == "True")
        det = caught / len(rs)
        blast = st.mean(int(r["clinical_blast_radius"]) for r in rs)
        tmean = st.mean(float(r["time_to_outcome_s"]) for r in rs)
        print(f"{arm:<12}{det:<18.1%}{blast:<20.1f}{tmean:.0f}")

    print("\n" + "=" * 64)
    print("PER FAULT — detection rate (caught / total)")
    print("=" * 64)
    faults = sorted({r["fault"] for r in rows})
    arms = sorted({r["arm"] for r in rows})
    print(f"{'fault':<22}" + "".join(f"{a:<14}" for a in arms))
    for fault in faults:
        line = f"{fault:<22}"
        for arm in arms:
            rs = [r for r in rows if r["fault"] == fault and r["arm"] == arm]
            caught = sum(1 for r in rs if r["caught"] == "True")
            line += f"{caught}/{len(rs):<12}"
        print(line)

    print("\n" + "=" * 64)
    print("PER FAULT — mean clinical blast radius")
    print("=" * 64)
    print(f"{'fault':<22}" + "".join(f"{a:<14}" for a in arms))
    for fault in faults:
        line = f"{fault:<22}"
        for arm in arms:
            rs = [r for r in rows if r["fault"] == fault and r["arm"] == arm]
            blast = st.mean(int(r["clinical_blast_radius"]) for r in rs) if rs else 0
            line += f"{blast:<14.1f}"
        print(line)

    print("\nInterpretation: infra-invisible faults (broken-reference, "
          "wrong-codesystem,\nbad-terminology, truncated-value) should show ~0 "
          "detection for baseline\nand high detection + low blast radius for treatment.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="path", default="experiment/results.csv")
    args = ap.parse_args()
    summarize(load(args.path))


if __name__ == "__main__":
    main()
