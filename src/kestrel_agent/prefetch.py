"""Bounded initial evidence for files explicitly named by the user."""
import re


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
                result = await engine.tools.execute("read_file", {"path": str(path), "max_lines": 1000})
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
