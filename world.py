"""A controllable, in-memory business world for refund-agent experiments."""

import sqlite3


SCHEMA = """
CREATE TABLE customers(id TEXT PRIMARY KEY, valid INTEGER NOT NULL);
CREATE TABLE payments(
    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, amount INTEGER NOT NULL, status TEXT NOT NULL
);
CREATE TABLE refunds(id INTEGER PRIMARY KEY AUTOINCREMENT, payment_id TEXT NOT NULL, amount INTEGER NOT NULL);
"""


class World:
    """Fresh state and fault-injectable tool implementations for one scenario."""

    def __init__(self, fixture, faults=None, approval_granted=True):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(SCHEMA)
        self.db.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [(row["id"], int(row["valid"])) for row in fixture["customers"]],
        )
        self.db.executemany(
            "INSERT INTO payments VALUES (?, ?, ?, ?)",
            [
                (row["id"], row["customer_id"], row["amount"], row["status"])
                for row in fixture["payments"]
            ],
        )
        self.faults = faults or {}
        self.approval_granted = approval_granted
        self.calls = []

    def call_tool(self, name, args):
        fault = self.faults.get(name)
        if fault == "timeout":
            result = {"error": "TIMEOUT"}
        elif fault == "error":
            result = {"error": "INTERNAL_ERROR"}
        elif fault == "malformed":
            result = "<<malformed tool response>>"
        else:
            result = getattr(self, f"_{name}")(**args)
        self.calls.append({"tool": name, "args": args, "result": result})
        return result

    def _get_customer(self, customer_id):
        row = self.db.execute("SELECT id, valid FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return {"id": row[0], "valid": bool(row[1])} if row else {"error": "NOT_FOUND"}

    def _get_payment(self, payment_id):
        row = self.db.execute(
            "SELECT id, customer_id, amount, status FROM payments WHERE id = ?", (payment_id,)
        ).fetchone()
        if not row:
            return {"error": "NOT_FOUND"}
        return {"id": row[0], "customer_id": row[1], "amount": row[2], "status": row[3]}

    # Intentionally permissive: agent errors must remain observable by the oracle.
    # Payment status is left untouched (refunds live in their own ledger) so a repeat
    # request is blocked only by the no-duplicate rule, not by the captured-only rule.
    def _issue_refund(self, payment_id):
        row = self.db.execute("SELECT amount FROM payments WHERE id = ?", (payment_id,)).fetchone()
        if not row:
            return {"error": "NOT_FOUND"}
        self.db.execute("INSERT INTO refunds(payment_id, amount) VALUES (?, ?)", (payment_id, row[0]))
        return {"status": "REFUNDED", "amount": row[0]}

    def _request_approval(self, payment_id):
        return {"approved": self.approval_granted}

    def refunds(self):
        return self.db.execute("SELECT payment_id, amount FROM refunds ORDER BY id").fetchall()
