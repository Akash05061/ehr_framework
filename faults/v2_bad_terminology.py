"""
fhir_mapping.py — the clinical logic layer.

THIS IS THE INJECTABLE SURFACE.

All construction of FHIR resources happens here and nowhere else. Your v2 fault
variants (Days 9-10) will be copies of THIS FILE with one surgical change each:
  - drop_required_field:   remove `status` from the Observation
  - wrong_code_system:     emit a code under the wrong system URI
  - broken_reference:      point Observation.subject at a non-existent Patient
  - truncated_value:       silently divide numeric values (data corruption)
  - bad_terminology:       emit a LOINC code that does not exist

Keep validation in the SERVICE permissive. The analyzer (Day 5-8) is what
catches these defects during a canary — not the service itself.
"""

# Bump this in each variant so you can see which version served a request.
VERSION = "v2-bad-terminology"

LOINC = "http://loinc.org"

# A few valid LOINC codes for common vitals/labs.
KNOWN_OBS_CODES = {
    "body_weight": ("29463-7", "Body weight"),
    "heart_rate": ("8867-4", "Heart rate"),
    "systolic_bp": ("8480-6", "Systolic blood pressure"),
    "glucose": ("2339-0", "Glucose [Mass/volume] in Blood"),
}


def build_patient(payload: dict) -> dict:
    """Construct a FHIR Patient from a simple admit payload."""
    return {
        "resourceType": "Patient",
        "name": [{
            "use": "official",
            "family": payload.get("family", "Doe"),
            "given": [payload.get("given", "Jane")],
        }],
        "gender": payload.get("gender", "unknown"),
        "birthDate": payload.get("birth_date", "1970-01-01"),
    }


def build_encounter(patient_id: str, payload: dict) -> dict:
    """Construct a FHIR Encounter referencing the admitted patient."""
    return {
        "resourceType": "Encounter",
        "status": "in-progress",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": payload.get("encounter_class", "IMP"),  # IMP = inpatient
        },
        "subject": {"reference": f"Patient/{patient_id}"},
    }


def build_observation(patient_id: str, payload: dict) -> dict:
    """Construct a FHIR Observation (a lab result or vital sign)."""
    kind = payload.get("kind", "heart_rate")
    code, display = KNOWN_OBS_CODES.get(kind, KNOWN_OBS_CODES["heart_rate"])
    value = payload.get("value", 72)

    return {
        "resourceType": "Observation",
        "status": "final",                       # <-- required; a variant drops this
        "code": {
            "coding": [{
                "system": LOINC,                 # <-- a variant corrupts this
                "code": "99999-9",               # BUG: nonexistent LOINC code
                "display": display,
            }],
        },
        "subject": {"reference": f"Patient/{patient_id}"},  # <-- a variant breaks this
        "valueQuantity": {
            "value": value,                      # <-- a variant truncates this
            "unit": payload.get("unit", "/min"),
            "system": "http://unitsofmeasure.org",
        },
    }


def validate_light(payload: dict) -> tuple[bool, str]:
    """
    Deliberately MINIMAL. Only rejects requests that are structurally unusable,
    NOT clinically incorrect ones. Clinical correctness is the analyzer's job.
    """
    if not isinstance(payload, dict):
        return False, "payload must be a JSON object"
    return True, ""
