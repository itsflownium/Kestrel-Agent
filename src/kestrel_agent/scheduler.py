"""Release read dependencies as they finish while serializing side effects."""
import asyncio

from .tools import READ_TOOLS


async def execute_plan(engine, plan, gate_prompt):
    running = {}
    statuses = engine.state['statuses']

    async def collect_one():
        done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
        for action_id, task in list(running.items()):
            if task in done:
                del running[action_id]
                task.result()
        engine.save()

    try:
        while running or any(a.id not in statuses for a in plan.actions):
            # Harvest completed reads before considering their newly ready descendants.
            for action_id, task in list(running.items()):
                if task.done():
                    del running[action_id]
                    task.result()
            remaining = engine.settings.max_steps - engine.state.get('steps', 0)
            if remaining <= 0:
                if running:
                    await collect_one()
                    continue
                if any(a.id not in statuses for a in plan.actions):
                    raise RuntimeError('Step budget reached; review /status before continuing.')
                break
            ready, changed = [], False
            for action in plan.actions:
                if action.id in statuses or action.id in running or not all(d in statuses for d in action.depends_on):
                    continue
                outcome = engine.dependency_outcome(action, statuses)
                if outcome == 'ready':
                    ready.append(action)
                else:
                    statuses[action.id] = outcome
                    changed = True
            reads = [a for a in ready if a.tool in READ_TOOLS]
            capacity = max(0, engine.settings.max_parallel_reads - len(running))
            selected = reads[:min(capacity, remaining)]
            # No effect runs concurrently with a read or another effect.
            if not reads and not running:
                selected = [a for a in ready if a.tool not in READ_TOOLS][:min(1, remaining)]
            if not selected:
                if running:
                    await collect_one()
                elif not changed and any(a.id not in statuses for a in plan.actions):
                    raise RuntimeError('No executable action; dependency state is inconsistent.')
                continue
            template = engine.store.template('gate', gate_prompt)
            # In standard mode the planner already chose unconditional actions.
            # Repeat semantic inference only for actual runtime conditions;
            # permission checks and deterministic dispatch validation still run.
            gated = [a for a in selected if engine.settings.agent_mode == 'jev' or a.condition.strip().lower() != 'always']
            decisions = {a.id: {'choice': 'execute', 'reason': 'Unconditional action from the selected model plan.'} for a in selected if a not in gated}
            questions = {a.id: {'instructions': f"{template}\nAction: {a.id}. Condition: {a.condition}.",
                'options': {'execute': 'The condition is satisfied and the action advances the task.',
                            'skip': 'The condition is false or the action is unrelated to the task.',
                            'need_context': 'Cannot determine from the evidence.'}} for a in gated}
            if questions:
                decisions.update(await engine.judge.decide({**engine.context(), 'actions': [a.model_dump() for a in gated]}, questions))
            engine.log('decisions', decisions)
            for action in selected:
                choice = decisions[action.id]['choice']
                engine.emit('decision', f'{action.id} → {choice}')
                if choice != 'execute':
                    statuses[action.id] = choice
                elif action.tool in READ_TOOLS:
                    running[action.id] = asyncio.create_task(engine.perform(action))
                else:
                    await engine.perform(action)
            engine.save()
            if running:
                await collect_one()
    finally:
        # Do not leave reads alive after interruption or a gate/provider failure.
        tasks = list(running.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
