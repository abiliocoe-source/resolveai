"""SQLite ticket log (standard library only). Only redacted messages are stored."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "resolveai.db"
SCHEMA = """CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, message TEXT, intent TEXT, status TEXT,
    reason TEXT, answer TEXT, citations TEXT, mode TEXT,
    review TEXT DEFAULT 'pending', review_note TEXT DEFAULT '', rating INTEGER)"""


class Store:
    def __init__(self, path=DEFAULT_DB):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(SCHEMA)

    def log(self, r) -> int:
        """r is an agent Result. Answered tickets need no review; others start as 'pending'."""
        review = "not_needed" if r.status == "answered" else "pending"
        cur = self.db.execute(
            "INSERT INTO tickets (created,message,intent,status,reason,answer,citations,mode,review) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), r.message, r.intent, r.status,
             r.reason, r.answer, json.dumps(r.citations), r.mode, review))
        self.db.commit()
        return cur.lastrowid

    def tickets(self, where: str = "", args: tuple = ()) -> list[dict]:
        rows = self.db.execute(f"SELECT * FROM tickets {where} ORDER BY id DESC", args).fetchall()
        return [{**dict(r), "citations": json.loads(r["citations"] or "[]")} for r in rows]

    def review(self, ticket_id: int, decision: str, note: str = "") -> None:
        if decision not in ("approved", "corrected", "rejected"):
            raise ValueError("decision must be approved, corrected or rejected")
        self.db.execute("UPDATE tickets SET review=?, review_note=? WHERE id=?", (decision, note[:500], ticket_id))
        self.db.commit()

    def rate(self, ticket_id: int, helpful: bool) -> None:
        self.db.execute("UPDATE tickets SET rating=? WHERE id=?", (int(helpful), ticket_id))
        self.db.commit()

    def stats(self) -> dict:
        t = self.tickets()
        n = len(t)
        rated = [x["rating"] for x in t if x["rating"] is not None]
        count = lambda key, val: sum(x[key] == val for x in t)
        return {
            "total": n,
            "by_intent": {i: count("intent", i) for i in sorted({x["intent"] for x in t})},
            "by_status": {s: count("status", s) for s in ("answered", "no_evidence", "escalated")},
            "escalation_rate": (count("status", "escalated") / n) if n else None,
            "pending_review": count("review", "pending"),
            "rated": len(rated),
            "helpful_rate": (sum(rated) / len(rated)) if rated else None,
        }
