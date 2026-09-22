"""Explicit user memory, separate from task evidence and learned procedures."""
from __future__ import annotations

import re
import time
from pathlib import Path

from .config import redact


class Memory:
    def __init__(self, store):
        self.store, self.db = store, store.db
        self.db.execute('''CREATE TABLE IF NOT EXISTS user_memory (
            scope TEXT NOT NULL, key TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
            created REAL NOT NULL, updated REAL NOT NULL, expires REAL, revision INTEGER NOT NULL,
            PRIMARY KEY(scope, key))''')
        self.db.commit()

    @staticmethod
    def scope(workspace: Path | None):
        return str(workspace.resolve()) if workspace is not None else '*'

    def put(self, key, content, *, workspace=None, kind='note', days=None):
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key):
            raise ValueError('Memory keys use lowercase letters, digits, underscores, and hyphens.')
        if kind not in {'note', 'preference'}:
            raise ValueError('Memory kind must be note or preference.')
        content = content.strip()
        if not 1 <= len(content) <= 2000:
            raise ValueError('Memory must contain 1–2000 characters.')
        if redact(content) != content:
            raise ValueError('Memory cannot store detected API keys or tokens.')
        if days is not None and (type(days) is not int or not 1 <= days <= 3650):
            raise ValueError('Expiration must be 1–3650 days.')
        scope = self.scope(workspace)
        exists = self.db.execute('SELECT 1 FROM user_memory WHERE scope=? AND key=?', (scope, key)).fetchone()
        if not exists and self.db.execute('SELECT count(*) FROM user_memory WHERE scope=?', (scope,)).fetchone()[0] >= 200:
            raise ValueError('At most 200 memory entries per scope; forget unused entries first.')
        from .config import check_storage
        check_storage(self.store.settings, len(content.encode()) * 3)
        now = time.time()
        expiry = now + days * 86400 if days else None
        self.db.execute('''INSERT INTO user_memory VALUES(?,?,?,?,?,?,?,1)
            ON CONFLICT(scope,key) DO UPDATE SET kind=excluded.kind,content=excluded.content,
                updated=excluded.updated,expires=excluded.expires,revision=user_memory.revision+1''',
            (scope, key, kind, content, now, now, expiry))
        self.db.commit()

    def list(self, workspace=None, *, include_global=True, include_expired=True):
        scope = self.scope(workspace)
        scopes = [scope, '*'] if include_global and scope != '*' else [scope]
        rows = self.db.execute('SELECT * FROM user_memory WHERE scope IN (' + ','.join('?' for _ in scopes) + ') ORDER BY updated DESC,key', scopes)
        now = time.time()
        return [{**dict(row), 'expired': row['expires'] is not None and row['expires'] <= now, 'source': 'explicit user entry'}
                for row in rows if include_expired or row['expires'] is None or row['expires'] > now]

    def forget(self, key, *, workspace=None):
        count = self.db.execute('DELETE FROM user_memory WHERE scope=? AND key=?', (self.scope(workspace), key)).rowcount
        self.db.commit()
        if not count:
            raise ValueError('No memory with that key in the selected scope.')

    def retrieve(self, query, workspace, max_chars=6000):
        terms = set(re.findall(r'[\w-]{3,}', query.casefold()))
        candidates = []
        rows = self.list(workspace, include_expired=False)
        project_keys = {row['key'] for row in rows if row['scope'] != '*'}
        for row in rows:
            if row['scope'] == '*' and row['key'] in project_keys:
                continue
            words = set(re.findall(r'[\w-]{3,}', (row['key'] + ' ' + row['content']).casefold()))
            score = len(terms & words)
            if row['kind'] == 'preference' or score:
                candidates.append((row['scope'] != '*', row['kind'] == 'preference', score, row['updated'], row))
        selected, used, seen = [], 0, set()
        for *_, row in sorted(candidates, key=lambda item: item[:4], reverse=True):
            # A project entry overrides the same global key, including its kind.
            if row['key'] in seen:
                continue
            seen.add(row['key'])
            size = len(row['content']) + len(row['key']) + 160
            if used + size > max_chars or len(selected) >= 8:
                continue
            used += size
            selected.append(row)
        return selected
