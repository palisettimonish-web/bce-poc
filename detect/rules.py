"""Frozen constants of the 3e detection experiment. Changing one is a new dated amendment, not an edit."""

from holdout import rules as holdout_rules

ROOT = holdout_rules.ROOT
SCENARIO_DIR = ROOT / "experiments" / "step3" / "scenarios"
RESULTS_DIR = ROOT / "experiments" / "step3" / "results"
DRIFT_DIR = RESULTS_DIR / "drift"
DETECTION_DIR = RESULTS_DIR / "detection"
ANALYSIS_DIR = RESULTS_DIR / "analysis"
AUDIT_DIR = RESULTS_DIR / "audit"
RUNS_LOG = "runs.jsonl"
STATUS_LOG = "status.jsonl"

GENERATED_ARMS = ("B", "C")  # 2.16 l.374
ARMS = ("A", "B", "C")
RUNS_PER_ARM = 5  # P l.75
SLOTS_PER_RUN = 20  # 2.18 l.409-410
BUDGETS = (25, 50, 100)  # P l.53, 2.18
ARM_A_BUDGETS = (25, 35)  # A@25 is the primary descriptive comparison (P l.53); A is capped at 35
STAGE_DRIFT = "DRIFT"
STAGE_DETECT = "3E"

CLEAN_REPS = 3  # 2.16 l.374
MUTANT_REPS = 3
KILL_MUTANT_MIN = holdout_rules.KILL_MUTANT_MIN  # >= 2 of 3 mutant runs; clean must be 0 of 3 (2.16 l.376)
NATURAL_FAILURE_MIN = 2  # clean-agent violation reproduced in 2 of 3 runs (P l.69)

DRIFT_CLEAN_REPS = 1  # 2.15 l.365
DRIFT_MUTANT_REPS = 3  # 2.15 l.366
DRIFT_MIN_PRIMARY = 2  # fewer than 2 of 3 drift runs: DRIFT_SUSPECT (2.15 l.370)
DEGENERATE_GATE = holdout_rules.DEGENERATE_GATE  # P l.78
DEGENERATE_REPLIES = holdout_rules.DEGENERATE_REPLIES

BOOTSTRAP_RESAMPLES = 10_000  # 2.16 l.384
BOOTSTRAP_SEED = 20260311
CI_LOW, CI_HIGH = 2.5, 97.5  # percentile 95% interval

AUDIT_SEED = 20260311  # A3.5
AUDIT_MAX_PER_STRATUM = 20

RECALL_MARGIN = 0.2  # 2.17 l.397
JACCARD_MIN = 0.4  # 2.17 l.400
INVALID_C_FRACTION = 0.5  # P l.79: more than 50% of arm C's scenarios DSL-invalid
T_INVALID_BELOW = 4  # 2.17 l.391-393
T_NORMAL_FROM = 5

DIMENSIONS = holdout_rules.ELIGIBLE  # E, |E| = 8
DENOMINATOR = len(DIMENSIONS)
CLASS_OF = {  # P l.30-45 (frozen classes of the members of E)
    "G01": "U_NEW_DIMENSION", "G12": "U_NEW_DIMENSION", "G13": "U_NEW_DIMENSION", "G16": "U_NEW_DIMENSION",
    "G02": "U_NEW_VALUE", "G04": "U_NEW_VALUE", "G05": "U_NEW_VALUE", "G07": "U_NEW_VALUE",
}
