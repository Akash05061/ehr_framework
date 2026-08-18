"""
signals.py — clinical-integrity signals.

Each signal is an independent, clinical-SEMANTIC check on a single Observation
the canary produced, compared against the ground-truth inputs the analyzer sent.
These are NOT syntactic (schema/null) checks: they catch defects that return
HTTP 200 and pass single-resource validation but are clinically wrong.

Mapping to fault variants (faults/ dir):
  referential_integrity <- v2_broken_reference   (FLAGSHIP: infra-invisible)
  terminology           <- v2_wrong_codesystem / v2_bad_terminology (infra-invisible)
  value_fidelity        <- v2_truncated_value     (infra-invisible)
  required_fields       <- v2_drop_status         (may surface as a write error too)
"""
import requests

KNOWN_SYSTEMS = {"http://loinc.org"}
KNOWN_LOINC = {"29463-7", "8867-4", "8480-6", "2339-0"}


def resolve_reference(fhir_base, reference, session):
    """GET a FHIR reference like 'Patient/123'. Returns True if it resolves (200)."""
    try:
        r = session.get(f"{fhir_base}/{reference}?_format=json", timeout=15)
        return r.status_code == 200
    except requests.RequestException:
        return False


def check_referential_integrity(obs, expected_patient_id, fhir_base, session):
    """FLAGSHIP: does Observation.subject resolve, and point to the right patient?"""
    subject = (obs.get("subject") or {}).get("reference", "")
    if not subject:
        return False, "missing subject reference"
    if not resolve_reference(fhir_base, subject, session):
        return False, f"dangling reference: {subject}"
    if subject != f"Patient/{expected_patient_id}":
        return False, f"subject points to wrong patient: {subject}"
    return True, ""


def check_terminology(obs):
    """Is the code under a known system and a known-valid code?"""
    coding = ((obs.get("code") or {}).get("coding") or [{}])[0]
    system = coding.get("system", "")
    code = coding.get("code", "")
    if system not in KNOWN_SYSTEMS:
        return False, f"unknown code system: {system}"
    if code not in KNOWN_LOINC:
        return False, f"invalid/unknown code: {code}"
    return True, ""


def check_required_fields(obs):
    """FHIR requires Observation.status and code."""
    if not obs.get("status"):
        return False, "missing required field: status"
    if not obs.get("code"):
        return False, "missing required field: code"
    return True, ""


def check_value_fidelity(obs, expected_value):
    """Did the stored value match what we sent? Catches silent truncation/corruption."""
    got = (obs.get("valueQuantity") or {}).get("value")
    if got is None:
        return False, "missing value"
    if abs(float(got) - float(expected_value)) > 1e-6:
        return False, f"value corrupted: sent {expected_value}, stored {got}"
    return True, ""


def evaluate_observation(obs, expected_patient_id, expected_value, fhir_base, session):
    """Run all signals. Returns (intact: bool, failures: dict[signal -> reason])."""
    failures = {}
    for name, ok, reason in [
        ("referential_integrity",
         *check_referential_integrity(obs, expected_patient_id, fhir_base, session)),
        ("terminology", *check_terminology(obs)),
        ("required_fields", *check_required_fields(obs)),
        ("value_fidelity", *check_value_fidelity(obs, expected_value)),
    ]:
        if not ok:
            failures[name] = reason
    return (len(failures) == 0), failures
