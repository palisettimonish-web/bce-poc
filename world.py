"""A controllable, in-memory business world for refund-agent experiments."""

import copy
import sqlite3


SCHEMA = """
CREATE TABLE customers(id TEXT PRIMARY KEY, valid INTEGER NOT NULL);
CREATE TABLE payments(
    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, amount INTEGER NOT NULL,
    currency TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE refunds(
    id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT NOT NULL, amount INTEGER NOT NULL,
    currency TEXT NOT NULL, created_seq INTEGER NOT NULL
);
"""

DEFAULT_CURRENCY = "INR"


def _normalize_fault(fault):
    """Accept the legacy string form ("timeout") or {"mode": ..., "phase": "before"|"after"}."""
    if fault is None:
        return None
    if isinstance(fault, str):
        return {"mode": fault, "phase": "before"}
    return {"mode": fault["mode"], "phase": fault.get("phase", "before")}


class World:
    """Fresh state and fault-injectable tool implementations for one scenario.

    The World is the environment only: it records what the agent does and never enforces
    business rules, so incorrect agent behavior stays observable to the oracle.
    """

    def __init__(self, fixture, faults=None, approval_granted=True):
        self.initial_state = copy.deepcopy(fixture)
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(SCHEMA)
        self.db.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [(row["id"], int(row["valid"])) for row in fixture["customers"]],
        )
        self.db.executemany(
            "INSERT INTO payments VALUES (?, ?, ?, ?, ?)",
            [
                (
                    row["id"],
                    row["customer_id"],
                    row["amount"],
                    row.get("currency", DEFAULT_CURRENCY),
                    row["status"],
                )
                for row in fixture["payments"]
            ],
        )
        self.faults = {tool: _normalize_fault(fault) for tool, fault in (faults or {}).items()}
        self.approval_granted = approval_granted
        self.calls = []
        self._clock = 0

    def _tick(self):
        self._clock += 1
        return self._clock

    def call_tool(self, name, args):
        fault = self.faults.get(name)
        applied = False
        if fault and fault["phase"] == "before":
            result = self._fault_result(fault["mode"])
        else:
            result = getattr(self, f"_{name}")(**args)
            applied = True
            if fault:  # phase == "after": the operation ran, but the response is lost
                result = self._fault_result(fault["mode"])
        self.calls.append({"tool": name, "args": args, "result": result, "applied": applied})
        return result

    @staticmethod
    def _fault_result(mode):
        if mode == "timeout":
            return {"error": "TIMEOUT"}
        if mode == "error":
            return {"error": "INTERNAL_ERROR"}
        if mode == "malformed":
            return "<<malformed tool response>>"
        raise ValueError(f"unknown fault mode: {mode}")

    def _get_customer(self, customer_id):
        row = self.db.execute("SELECT id, valid FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return {"id": row[0], "valid": bool(row[1])} if row else {"error": "NOT_FOUND"}

    def _get_payment(self, payment_id):
        row = self.db.execute(
            "SELECT id, customer_id, amount, currency, status FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if not row:
            return {"error": "NOT_FOUND"}
        refunded = self.db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE payment_id = ?", (payment_id,)
        ).fetchone()[0]
        return {
            "id": row[0],
            "customer_id": row[1],
            "amount": row[2],
            "currency": row[3],
            "status": row[4],
            "refunded_amount": refunded,
        }

    # Intentionally permissive: agent errors must remain observable by the oracle.
    # Payment status is left untouched (refunds live in their own ledger) so a repeat
    # request is judged on the ledger, not masked by a status change.
    def _issue_refund(self, payment_id):
        row = self.db.execute(
            "SELECT amount, currency FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if not row:
            return {"error": "NOT_FOUND"}
        self.db.execute(
            "INSERT INTO refunds(payment_id, amount, currency, created_seq) VALUES (?, ?, ?, ?)",
            (payment_id, row[0], row[1], self._tick()),
        )
        return {"status": "REFUNDED", "amount": row[0], "currency": row[1]}

    def _request_approval(self, payment_id):
        return {"approved": self.approval_granted}

    def refunds(self):
        return self.db.execute("SELECT payment_id, amount FROM refunds ORDER BY id").fetchall()

    def ledger(self):
        rows = self.db.execute(
            "SELECT payment_id, amount, currency, created_seq FROM refunds ORDER BY id"
        ).fetchall()
        return [
            {"payment_id": r[0], "amount": r[1], "currency": r[2], "created_seq": r[3]} for r in rows
        ]
