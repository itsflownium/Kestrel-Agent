"""Synthetic read-DAG latency experiment; no model calls or Codex comparison."""
import asyncio
import hashlib
import json
import random
import time
from pathlib import Path
from types import SimpleNamespace as NS

from kestrel_agent.schema import Action, Plan
from kestrel_agent.scheduler import execute_plan


def make_plan():
    return Plan(mode='plan', message='', success_criteria=[], actions=[
        Action(id=name, tool='read_file', arguments_json='{}', depends_on=deps,
               purpose='Synthetic read', condition='always')
        for name, deps in [('fast', []), ('slow', []), ('child', ['fast'])]])


async def trial(mode):
    plan = make_plan()
    trace = []
    start = time.perf_counter()
    state = {'steps': 0, 'statuses': {}}
    async def perform(action):
        state['steps'] += 1
        trace.append({'action': action.id, 'event': 'start', 'seconds': time.perf_counter() - start})
        await asyncio.sleep(.02 if action.id == 'fast' else .2)
        state['statuses'][action.id] = 'completed'
        trace.append({'action': action.id, 'event': 'finish', 'seconds': time.perf_counter() - start})
    async def decide(context, questions):
        return {key: {'choice': 'execute'} for key in questions}
    engine = NS(state=state, settings=NS(max_steps=24, max_parallel_reads=4), perform=perform,
        dependency_outcome=lambda action, statuses: 'ready', context=lambda: {},
        judge=NS(decide=decide), store=NS(template=lambda key, default: default),
        log=lambda *a: None, emit=lambda *a: None, save=lambda: None)
    if mode == 'batch_barrier':
        while len(state['statuses']) < len(plan.actions):
            ready = [a for a in plan.actions if a.id not in state['statuses'] and all(d in state['statuses'] for d in a.depends_on)]
            await decide({}, {a.id: {} for a in ready})
            await asyncio.gather(*(perform(a) for a in ready))
    else:
        await execute_plan(engine, plan, '')
    elapsed = time.perf_counter() - start
    assert set(state['statuses']) == {'fast', 'slow', 'child'}
    return {'mode': mode, 'seconds': elapsed, 'trace': trace, 'passed': True}


async def main():
    rng = random.Random(20260921)
    results = []
    for repetition in range(1, 6):
        modes = ['batch_barrier', 'dependency_driven']
        rng.shuffle(modes)
        for mode in modes:
            results.append({'repetition': repetition, **await trial(mode)})
    source = Path(__file__).resolve().parents[1] / 'src/kestrel_agent/scheduler.py'
    Path('benchmarks/results-scheduling.json').write_text(json.dumps({
        'scheduler_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'description': 'Synthetic 20ms fast read, 200ms unrelated read, 200ms fast-read descendant; instantaneous mocked Jev.',
        'results': results}, indent=2))
    for mode in ['batch_barrier', 'dependency_driven']:
        import statistics
        print(mode, 'median seconds', round(statistics.median(r['seconds'] for r in results if r['mode'] == mode), 4))


if __name__ == '__main__':
    asyncio.run(main())
