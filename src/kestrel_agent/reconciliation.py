"""Conservative subgraph reuse and normalized effect identities."""
import asyncio
import hashlib
import json
from pathlib import Path

EFFECTS = {'write_file', 'shell', 'mcp'}


def effect_identity(tool, arguments, workspace):
    from .tool_contracts import validate_arguments
    args = validate_arguments(tool, arguments)
    def path(value):
        p = Path(value).expanduser()
        return str((workspace / p).resolve())
    if tool == 'write_file':
        args = {'path': path(args['path']), 'content': args['content']}
        family = [tool, args['path']]
    elif tool == 'shell':
        args['cwd'] = path(args['cwd'])
        argv = list(args['command'])
        # Normalize only explicit executable paths. Do not reinterpret options,
        # shell programs, quoting, environment variables, or arbitrary operands.
        if '/' in argv[0]:
            argv[0] = str((Path(args['cwd']) / argv[0]).resolve())
        script = None
        if Path(argv[0]).name in {'python', 'python3', 'node', 'ruby', 'bash', 'sh'} and len(argv) > 1 and not argv[1].startswith('-'):
            argv[1] = str((Path(args['cwd']) / argv[1]).resolve())
            script = argv[1]
        args['command'] = argv
        family = [tool, args['cwd'], argv[0], script]
    else:
        family = [tool, args['server'], args['tool']]
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return digest([tool, args]), digest(family)


def unresolved_effect(state, fingerprint, family):
    for entry in reversed(state.get('effect_receipts', [])):
        if entry['status'] == 'completed':
            continue
        audit = entry.get('workspace_audit') or {}
        if entry['fingerprint'] == fingerprint or (
            entry['family'] == family and audit.get('unchanged_at_boundaries') is not True
        ):
            return entry
    return None


async def repair_state(state, plan, tools):
    """Keep only an unchanged successful subgraph with fresh local sources."""
    previous = state.get('repair_snapshot') or {}
    old_actions = {a['id']: a for a in previous.get('actions', [])}
    results, statuses = {}, {}
    remaining = list(plan.actions)
    while remaining:
        ready = [a for a in remaining if all(d not in {x.id for x in remaining} for d in a.depends_on)]
        if not ready:
            break  # Plan validation normally prevents this.
        for action in ready:
            remaining.remove(action)
            if previous.get('statuses', {}).get(action.id) != 'completed' or old_actions.get(action.id) != action.model_dump():
                continue
            if any(d not in statuses for d in action.depends_on):
                continue
            result = previous.get('results', {}).get(action.id)
            if result is None:
                continue
            reusable = action.tool in EFFECTS
            if action.tool == 'read_file':
                from .schema import bind
                try:
                    observed = await asyncio.to_thread(tools.read_file, bind(action.arguments(), results))
                    reusable = isinstance(result, dict) and result.get('sha256') == observed.get('sha256') and result.get('path') == observed.get('path')
                except (OSError, ValueError, KeyError, TypeError):
                    reusable = False
            elif action.tool == 'write_file':
                try:
                    current = await asyncio.to_thread(tools.read_file, {'path': result['path'], 'max_lines': 1})
                    reusable = current.get('sha256') == result.get('sha256')
                except (OSError, ValueError, KeyError, TypeError):
                    reusable = False
            if reusable:
                results[action.id], statuses[action.id] = result, 'completed'
    state.update(plan=plan.model_dump(), results=results, statuses=statuses)
    return list(statuses)


def checkpoint(state, plan):
    state['repair_snapshot'] = {'actions': [a.model_dump() for a in plan.actions],
                                'results': dict(state['results']), 'statuses': dict(state['statuses'])}
