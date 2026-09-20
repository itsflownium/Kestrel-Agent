"""Bounded answer candidates from completed terminal actions, without generation."""
import re
import shlex

from .schema import Plan, bind

LIMIT = 12000


def fenced(text: str) -> str:
    fence = '`' * max(3, 1 + max((len(m[0]) for m in re.finditer(r'`+', text)), default=0))
    return f'{fence}\n{text}\n{fence}'


def candidates(plan: Plan, results: dict, statuses: dict) -> dict[str, dict]:
    """Consider only completed leaf actions; Jev must still verify the entire task."""
    consumed = {dep for action in plan.actions if statuses.get(action.id) == 'completed' for dep in action.depends_on}
    options = {}

    def add(action, kind, text):
        if isinstance(text, str) and text.strip() and len(text) <= LIMIT and text not in {v['text'] for v in options.values()}:
            options[f'answer_{len(options)}'] = {'action': action.id, 'kind': kind, 'text': text}

    for action in reversed(plan.actions):
        if action.id in consumed or statuses.get(action.id) != 'completed':
            continue
        result = results.get(action.id)
        if not isinstance(result, dict) or result.get('error') or any(result.get(k) for k in ('truncated', 'possibly_truncated', 'output_truncated')):
            continue
        if action.tool == 'shell':
            if type(result.get('exitCode')) is not int or result['exitCode'] != 0:
                continue
            stdout, stderr = result.get('stdout', ''), result.get('stderr', '')
            if not isinstance(stdout, str) or not isinstance(stderr, str) or len(stdout) + len(stderr) > LIMIT:
                continue
            if not stderr:
                add(action, 'stdout', stdout)
            try:
                args = bind(action.arguments(), results)
                argv = args.get('command')
                if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
                    continue
                receipt = 'Command:\n' + fenced(shlex.join(argv)) + '\nExit code: 0'
                if stdout:
                    receipt += '\n\nStandard output:\n' + fenced(stdout.rstrip('\n'))
                if stderr:
                    receipt += '\n\nStandard error:\n' + fenced(stderr.rstrip('\n'))
                add(action, 'command_receipt', receipt)
            except (KeyError, ValueError, IndexError, TypeError):
                continue
        elif action.tool == 'query_table':
            add(action, 'json_content', result.get('json_content'))
        elif action.tool == 'generate':
            add(action, 'content', result.get('content'))
        if len(options) >= 3:
            break
    return dict(list(options.items())[:3])
