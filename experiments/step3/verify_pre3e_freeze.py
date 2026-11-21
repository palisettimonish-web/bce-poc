"""Pre-3e freeze check (Amendment 4, superseded by Amendment 5: it now verifies pre3e_freeze_a5.json). Verification only; it writes nothing and calls no model.

Run from the repository root before every 3e call:
    PYTHONPATH=. python experiments/step3/verify_pre3e_freeze.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from detect import preflight  # noqa: E402

if __name__ == "__main__":
    issues = preflight.verify()
    print("OK: pre-3e freeze verified" if not issues else "\n".join(issues))
    sys.exit(1 if issues else 0)
