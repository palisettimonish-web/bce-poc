"""Frozen thresholds, stage order and statuses from Amendment 2 (preregistration section 2).

These are constants of the experimental contract. Changing one is a new dated amendment, not an edit.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_DIR = ROOT / "holdout"
VALIDATION_DIR = ROOT / "experiments" / "step3" / "holdout_validation"
MANIFEST_DIR = ROOT / "experiments" / "step3" / "manifests"

STAGES = ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7")  # 2.1: fixed order, batchwise

ELIGIBLE = ("G01", "G02", "G04", "G05", "G07", "G12", "G13", "G16")  # preregistration line 48
MAX_PER_DIMENSION = 3  # A6
MAX_CANDIDATES = 24
CANDIDATE_ID_PATTERN = r"^M\d{2}$"

PASS = "PASS"
ADMITTED = "ADMITTED"
TERMINAL_STATUSES = (
    "NO_CANDIDATE",
    "CATALOGUE_VIOLATION",
    "DSL_INEXPRESSIBLE",
    "ORACLE_UNDETECTABLE",
    "CLEAN_NOT_CLEAN",
    "STOCHASTIC_ADMISSION_FAILURE",
    "UNINTENDED_EFFECT",
    "NEUTRAL_CONTROL_FAILURE",
    "ALREADY_COVERED_BY_BASELINE",
    "CROSS_TRIGGER_NON_SPECIFIC",
    "VARIANT_EQUIVALENT",
    "CONSTRUCT_REVIEW_FAILURE",
)  # 2.11 (there is deliberately no replacement status: 2.12)

N_TRIGGER = 3  # 2.4
N_NEUTRAL = 2
MAX_EDIT_SENTENCES = 2  # 2.2 (1)

S1_REPS = 10  # per trigger instance (2.6)
S2_REPS = 10
S2_MIN_PRIMARY = 7  # primary code in >= 7/10 on every instance
S2_UNINTENDED_FAIL = 2  # non-intended code in >= 2/10 on any instance
S3_REPS = 5  # per neutral instance (2.7)
S3_NEUTRAL_FAIL = 2  # primary code in >= 2 of the 10 neutral runs
S4_REPS = 3  # per baseline scenario (2.8)
KILL_MUTANT_MIN = 2  # mutant runs (of 3) with the code; clean must have 0 of 3
S5_REPS = 3  # (2.9)
S5_FIRE_MIN = 1
S5_NONSPECIFIC_DIMS = 2
S6_REPS = 10
S6_EQUIVALENT_MIN = 7
DEGENERATE_GATE = 0.10  # line 78: more than 10% empty / max-turn replies stops the run
DEGENERATE_REPLIES = ("[agent returned no text]", "[max turns exceeded]")
REVIEW_SEED = 20260311  # 2.10
REVIEW_ITEMS = ("1", "2", "3", "4", "5", "6")
TRANSPORT_ATTEMPTS = 3  # 2.14

_CATALOGUE = None


def catalogue():
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = json.loads((HOLDOUT_DIR / "catalogue.json").read_text(encoding="utf-8"))
    return _CATALOGUE


def all_known_codes():
    cat = catalogue()
    return set(cat["allowed_primary_codes"]) | set(cat["forbidden_codes"]) | set(cat["other_known_codes"]) | {
        c for c in cat["oracle_rule_text"]
    }
