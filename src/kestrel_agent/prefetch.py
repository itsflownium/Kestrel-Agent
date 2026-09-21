"""Bounded initial evidence for files explicitly named by the user."""
import re
import hashlib


async def prefetch(engine, request: str) -> None:
    names = list(dict.fromkeys(re.findall(
        r"(?<![\w/])[\w./-]+\.(?:json|csv|md|txt|py|js|ts|toml|yaml|yml)\b", request)))
    if len(names) > 4:
        return
    for index, name in enumerate(names):
        # Leave room for the normal controller to finish even with tiny budgets.
        if engine.state.get("steps", 0) >= engine.settings.max_steps - 1:
            break
        # Respect requests whose explicit ordering makes early inspection inappropriate.
        if re.search(r"\b(?:run|execute)\b", request, re.I) and name.endswith((".py", ".js", ".ts")):
            continue
        try:
            path = engine.tools.path(name)
            if path.is_file() and path.stat().st_size <= 12000:
                result = getattr(engine, "initial_evidence", {}).get(str(path))
                if not result or not result.get("sha256") or hashlib.sha256(path.read_bytes()).hexdigest() != result["sha256"]:
                    result = await engine.tools.execute("read_file", {"path": str(path), "max_lines": 1000})
                else:
                    engine.log("initial_evidence_reuse", {"path": str(path), "sha256": result["sha256"]})
                tool = "read_file"
            elif not path.exists():
                result = {"path": str(path), "exists": False,
                          "note": "Absent at inspection time; write_file still checks for existing content before writing."}
                tool = "inspect_path"
            else:
                continue
        except (OSError, ValueError, PermissionError, UnicodeError):
            continue
        eid = engine.store.evidence(engine.sid, result)
        engine.state.setdefault("observations", []).append({
            "action": f"prefetch_{index}", "tool": tool, "status": "completed",
            "arguments": {"path": str(path)}, "evidence_id": eid, "result": result})
        engine.state["steps"] = engine.state.get("steps", 0) + 1
        engine.log("prefetch", {"tool": tool, "path": str(path), "evidence_id": eid})
    engine.save()
