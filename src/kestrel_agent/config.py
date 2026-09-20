from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

REPO = Path(__file__).resolve().parents[2]
HARD_STORAGE_LIMIT = 3_000_000_000


def home() -> Path:
    default = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "kestrel"
    return Path(os.environ.get("KESTREL_HOME", str(default))).expanduser().resolve()


def load_secrets() -> None:
    # A workspace's .env is task data, never implicit application configuration.
    load_dotenv(home() / "secrets.env", override=False)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    model: str | None = None
    effort: Literal["low", "medium", "high"] = "low"
    jev_model: str = "jev-1.13"
    permission: Literal["read-only", "workspace", "full"] = "workspace"
    readable_roots: list[str] = []
    writable_roots: list[str] = []
    network: bool = True
    shell: bool = True
    confirm_shell: bool = True
    confirm_writes: bool = False
    mcp_auto_allow: list[str] = []
    max_steps: int = Field(default=24, ge=1, le=200)
    max_model_calls: int = Field(default=6, ge=1, le=30)
    max_jev_calls: int = Field(default=32, ge=1, le=300)
    max_minutes: int = Field(default=15, ge=1, le=180)
    command_timeout_seconds: int = Field(default=120, ge=1, le=1800)
    max_context_chars: int = Field(default=24000, ge=4000, le=100000)
    max_storage_bytes: int = Field(default=2_800_000_000, ge=100_000_000, le=HARD_STORAGE_LIMIT)
    # Optional user-supplied rate. Subscription usage is never represented as API dollars.
    jev_input_dollars_per_million: float | None = Field(default=None, ge=0)

    @classmethod
    def load(cls) -> "Settings":
        file = home() / "config.json"
        return cls.model_validate_json(file.read_text()) if file.exists() else cls()

    def save(self) -> None:
        home().mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(home() / "config.json", self.model_dump_json(indent=2))


def atomic_write(path: Path, text: str, mode: int = 0o600) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w") as f:
            os.fchmod(f.fileno(), mode)
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def redact(text: str) -> str:
    text = re.sub(r"apikey_[A-Za-z0-9_]+", "[REDACTED_JEV_KEY]", text)
    text = re.sub(r"\b(?:sk-|ghp_|gho_)[A-Za-z0-9_-]{16,}", "[REDACTED_TOKEN]", text)
    key = os.environ.get("TYPESAFE_API_KEY")
    return text.replace(key, "[REDACTED_JEV_KEY]") if key else text


def storage_bytes() -> int:
    """Count managed storage once, including the installed interpreter environment."""
    roots = [REPO, home(), Path(sys.prefix)]
    seen: set[tuple[int, int]] = set()
    total = 0
    for root in roots:
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not Path(directory, d).is_symlink()]
            for name in files:
                try:
                    stat = Path(directory, name).lstat()
                    identity = (stat.st_dev, stat.st_ino)
                    if identity not in seen:
                        seen.add(identity)
                        total += stat.st_size
                except OSError:
                    continue
    return total


def check_storage(settings: Settings, additional: int = 0) -> int:
    used = storage_bytes()
    if used + additional >= settings.max_storage_bytes:
        raise RuntimeError("Kestrel storage limit reached. Export/remove old sessions before continuing.")
    return used
