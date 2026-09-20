from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ToolName = Literal["list_files", "read_file", "search_files", "write_file", "shell", "fetch_url", "mcp", "generate", "research", "choose", "read_evidence", "query_table"]


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    tool: ToolName
    arguments_json: str
    depends_on: list[str]
    purpose: str
    condition: str

    def arguments(self) -> dict[str, Any]:
        value = json.loads(self.arguments_json)
        if not isinstance(value, dict):
            raise ValueError("Action arguments must be a JSON object.")
        return value


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["answer", "plan", "clarify"]
    message: str
    actions: list[Action] = Field(max_length=12)
    success_criteria: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def valid_graph(self) -> "Plan":
        ids = {a.id for a in self.actions}
        if len(ids) != len(self.actions):
            raise ValueError("Action IDs must be unique.")
        if self.mode == "plan" and not self.actions:
            raise ValueError("An execution plan needs actions.")
        if self.mode != "plan" and self.actions:
            raise ValueError("Direct answers and clarification cannot execute tools.")
        for action in self.actions:
            action.arguments()
            if any(d not in ids or d == action.id for d in action.depends_on):
                raise ValueError("Invalid dependency.")
            refs = re.findall(r"\$\{([a-z][a-z0-9_]*)\.", action.arguments_json)
            if any(ref not in action.depends_on for ref in refs):
                raise ValueError("Argument references must name a declared dependency.")
        remaining = {a.id: set(a.depends_on) for a in self.actions}
        while remaining:
            ready = {k for k, deps in remaining.items() if not deps}
            if not ready:
                raise ValueError("Cyclic dependency graph.")
            remaining = {k: v - ready for k, v in remaining.items() if k not in ready}
        return self


def bind(value: Any, results: dict[str, Any]) -> Any:
    """Resolve structured result references; never evaluate generated code."""
    if isinstance(value, dict):
        return {k: bind(v, results) for k, v in value.items()}
    if isinstance(value, list):
        return [bind(v, results) for v in value]
    if not isinstance(value, str):
        return value

    def lookup(reference: str) -> Any:
        parts = reference.split(".")
        current: Any = results
        for part in parts:
            current = current[int(part)] if isinstance(current, list) else current[part]
        return current

    full = re.fullmatch(r"\$\{([^}]+)\}", value)
    if full:
        return lookup(full.group(1))
    return re.sub(r"\$\{([^}]+)\}", lambda m: str(lookup(m.group(1))), value)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            if item.get("type") == "object":
                item["additionalProperties"] = False
                item["required"] = list(item.get("properties", {}))
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(schema)
    return schema
