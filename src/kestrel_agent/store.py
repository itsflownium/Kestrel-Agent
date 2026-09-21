from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .config import Settings, check_storage, home, redact


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        home().mkdir(parents=True, exist_ok=True, mode=0o700)
        check_storage(settings, 1_000_000)
        self.db = sqlite3.connect(home() / "sessions.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created REAL, workspace TEXT, title TEXT, state TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, session TEXT, created REAL, kind TEXT, body TEXT);
        CREATE INDEX IF NOT EXISTS events_session ON events(session, id);
        CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY, session TEXT, created REAL, body TEXT);
        CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY, name TEXT, body TEXT, active INTEGER DEFAULT 0, created REAL);
        CREATE VIRTUAL TABLE IF NOT EXISTS workflow_search USING fts5(id UNINDEXED, name, body);
        CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY, body TEXT, created REAL);
        """)

    def create(self, workspace: Path, title: str = "New conversation") -> str:
        sid = uuid.uuid4().hex[:12]
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (sid, time.time(), str(workspace), title[:100], "{}"))
        self.db.commit()
        return sid

    def session(self, sid: str) -> dict:
        row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown session: {sid}")
        return dict(row)

    def sessions(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT id,created,workspace,title FROM sessions ORDER BY created DESC LIMIT 30")]

    def save_state(self, sid: str, state: dict) -> None:
        text = redact(json.dumps(state, ensure_ascii=False))
        check_storage(self.settings, len(text.encode()) * 3)
        self.db.execute("UPDATE sessions SET state=? WHERE id=?", (text, sid))
        self.db.commit()

    def event(self, sid: str, kind: str, body: Any) -> None:
        text = redact(json.dumps(body, ensure_ascii=False, default=str))
        if len(text) > 150_000:
            text = json.dumps({"truncated": True, "preview": text[:140_000]}, ensure_ascii=False)
        check_storage(self.settings, len(text.encode()) * 3)
        self.db.execute("INSERT INTO events(session,created,kind,body) VALUES(?,?,?,?)", (sid, time.time(), kind, text))
        self.db.commit()

    def history(self, sid: str, limit: int = 30) -> list[dict]:
        rows = self.db.execute("SELECT kind,body FROM events WHERE session=? ORDER BY id DESC LIMIT ?", (sid, limit))
        return [{"kind": r[0], "body": json.loads(r[1])} for r in reversed(list(rows))]

    def conversation(self, sid: str, limit: int = 6) -> list[dict]:
        rows = self.db.execute("SELECT kind,body FROM events WHERE session=? AND kind IN ('user','assistant') ORDER BY id DESC LIMIT ?", (sid, limit))
        return [{"kind": r[0], "body": json.loads(r[1])} for r in reversed(list(rows))]

    def evidence(self, sid: str, body: Any) -> str:
        text = redact(json.dumps(body, ensure_ascii=False, default=str))
        if len(text.encode()) > 1_000_000:
            raise ValueError("Tool result exceeds 1 MB; narrow the request or use pagination.")
        check_storage(self.settings, len(text.encode()) * 3)
        eid = uuid.uuid4().hex[:16]
        self.db.execute("INSERT INTO evidence VALUES(?,?,?,?)", (eid, sid, time.time(), text))
        self.db.commit()
        return eid

    def read_evidence(self, sid: str, eid: str) -> Any:
        row = self.db.execute("SELECT body FROM evidence WHERE id=? AND session=?", (eid, sid)).fetchone()
        if row is None:
            raise ValueError("Evidence is not available in this session.")
        return json.loads(row[0])

    def search_evidence(self, sid: str, query: str, offset: int = 0, limit: int = 10) -> dict:
        if len(query) > 500:
            raise ValueError("Evidence search query exceeds 500 characters.")
        offset, limit = max(0, offset), min(20, max(1, limit))
        rows = list(self.db.execute(
            "SELECT id,created,body FROM evidence WHERE session=? AND instr(lower(body), lower(?)) > 0 ORDER BY created,id LIMIT ? OFFSET ?",
            (sid, query, limit + 1, offset)))
        results = []
        for row in rows[:limit]:
            text = json.dumps(json.loads(row['body']), ensure_ascii=False)
            start = max(0, text.lower().find(query.lower()) - 100)
            results.append({'evidence_id': row['id'], 'created': row['created'], 'offset': start,
                            'excerpt': text[start:start + 800], 'total_chars': len(text)})
        return {'matches': results, 'next_offset': offset + limit if len(rows) > limit else None,
                'historical_snapshots': True}

    def search_workflows(self, query: str) -> list[dict]:
        words = re.findall(r"[a-zA-Z]{3,}", query)[:12]
        if not words:
            return []
        rows = self.db.execute("""SELECT w.id,w.name,w.body FROM workflow_search f
            JOIN workflows w ON f.id=w.id WHERE workflow_search MATCH ? AND w.active=1
            ORDER BY rank LIMIT 3""", (" OR ".join('"' + w + '"' for w in words),))
        return [dict(r) for r in rows]

    def add_workflow(self, name: str, body: str) -> str:
        wid = uuid.uuid4().hex[:10]
        self.db.execute("INSERT INTO workflows VALUES(?,?,?,?,?)", (wid, name, body, 0, time.time()))
        self.db.execute("INSERT INTO workflow_search VALUES(?,?,?)", (wid, name, body))
        self.db.commit()
        return wid

    def activate(self, wid: str, active: bool = True) -> None:
        cursor = self.db.execute("UPDATE workflows SET active=? WHERE id=?", (int(active), wid))
        self.db.commit()
        if not cursor.rowcount:
            raise ValueError("Unknown workflow ID.")

    def template(self, name: str, default: str) -> str:
        row = self.db.execute("SELECT body FROM templates WHERE id=?", (name,)).fetchone()
        return row[0] if row else default

    def close(self) -> None:
        self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.db.close()
