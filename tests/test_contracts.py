"""Offline checks prepared for later authorization; not run during build."""

import json

import pytest
from pydantic import ValidationError

from kestrel_agent.config import Settings, redact
from kestrel_agent.schema import Plan, bind
from kestrel_agent.tools import ToolExecutor


def action(name, dependencies=(), arguments=None):
    return {"id": name, "tool": "read_file", "arguments_json": json.dumps(arguments or {"path": "note.txt"}),
            "depends_on": list(dependencies), "purpose": "Read evidence", "condition": "always"}


def plan(actions):
    return Plan.model_validate({"mode": "plan", "message": "Read sources", "actions": actions, "success_criteria": []})


def test_cycles_are_rejected():
    with pytest.raises(ValidationError):
        plan([action("a", ["b"]), action("b", ["a"])])


def test_reference_requires_declared_dependency():
    with pytest.raises(ValidationError):
        plan([action("a"), action("b", arguments={"path": "${a.path}"})])


def test_binding_preserves_types_without_evaluating_code():
    result = bind({"values": "${a.items}", "literal": "$(touch /tmp/not-executed)"}, {"a": {"items": [1, 2]}})
    assert result["values"] == [1, 2]
    assert result["literal"] == "$(touch /tmp/not-executed)"


def test_direct_answer_cannot_hide_actions():
    with pytest.raises(ValidationError):
        Plan.model_validate({"mode": "answer", "message": "Done", "actions": [action("a")], "success_criteria": []})


def test_workspace_boundary_and_symlink(tmp_path):
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "escape").symlink_to(outside, target_is_directory=True)
    tools = ToolExecutor(Settings(), workspace, None, None, None, "test", None)
    with pytest.raises(PermissionError):
        tools.path("escape/file.txt", write=True)


def test_read_only_rejects_write(tmp_path):
    tools = ToolExecutor(Settings(permission="read-only"), tmp_path, None, None, None, "test", None)
    with pytest.raises(PermissionError):
        tools.path("file.txt", write=True)


def test_storage_cannot_exceed_three_gb():
    with pytest.raises(ValidationError):
        Settings(max_storage_bytes=3_000_000_001)


def test_tokens_are_redacted():
    assert "apikey_" not in redact("example apikey_fake_test_value")
