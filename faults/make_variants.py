#!/usr/bin/env python3
"""
make_variants.py — generate the five fault variants from the clean mapping file.

Each variant is fhir_mapping.py with ONE surgical change + a bumped VERSION.
This keeps the experiment clean: v1 vs any variant differ by exactly one line.
Run from repo root:  python faults/make_variants.py
"""
import pathlib

BASE = pathlib.Path("app/clinical-service/fhir_mapping.py").read_text()
OUT = pathlib.Path("faults")

# Each variant: (filename, version, (old_substring, new_substring))
VARIANTS = [
    # FLAGSHIP — infra-invisible: Observation.subject points to a nonexistent Patient.
    ("v2_broken_reference.py", "v2-broken-ref", (
        '"subject": {"reference": f"Patient/{patient_id}"},  # <-- a variant breaks this',
        '"subject": {"reference": "Patient/does-not-exist-0000"},  # BUG: dangling reference',
    )),
    # infra-invisible: code emitted under the wrong system URI.
    ("v2_wrong_codesystem.py", "v2-wrong-codesystem", (
        '"system": LOINC,                 # <-- a variant corrupts this',
        '"system": "http://example.org/WRONG",  # BUG: wrong code system',
    )),
    # infra-invisible: a LOINC code that does not exist.
    ("v2_bad_terminology.py", "v2-bad-terminology", (
        '"code": code,                    # <-- a variant sends a fake code',
        '"code": "99999-9",               # BUG: nonexistent LOINC code',
    )),
    # infra-invisible: numeric value silently halved (data corruption).
    ("v2_truncated_value.py", "v2-truncated-value", (
        '"value": value,                      # <-- a variant truncates this',
        '"value": value // 2,                 # BUG: silently halves the value',
    )),
    # BORDERLINE — may surface as a write error (5xx) the infra gate also catches.
    ("v2_drop_status.py", "v2-drop-status", (
        '"status": "final",                       # <-- required; a variant drops this',
        '"_status_dropped": "final",              # BUG: required status field removed',
    )),
]

for filename, version, (old, new) in VARIANTS:
    text = BASE.replace('VERSION = "v1-clean"', f'VERSION = "{version}"')
    assert old in text, f"anchor not found for {filename!r} -- base file changed?"
    text = text.replace(old, new)
    (OUT / filename).write_text(text)
    print(f"wrote faults/{filename:28s} ({version})")

print("\nAll five variants generated.")
