from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from .config import Settings, atomic_write, home
from .engine import GATE_PROMPT, VERIFY_PROMPT
from .providers import Judge, Runtime
from .store import Store


async def learn_workflow(store: Store, settings: Settings, sid: str, emit) -> str:
    record = store.session(sid)
    state = json.loads(record["state"])
    if state.get("status") != "completed":
        raise ValueError("Only completed sessions can propose workflow candidates.")
    runtime = Runtime(settings, Path(record["workspace"]), emit)
    try:
        text = await runtime.complete(
            "Extract a reusable task procedure from this successful trace. Return concise Markdown: "
            "a title, applicability conditions, parameter names, steps, bounded Jev decisions, "
            "completion checks, and failure cases. Replace instance-specific paths/names/data with parameters. "
            "Never include secrets. This is a candidate recipe, not executable code or authorization.\n"
            + json.dumps(store.history(sid, 60), default=str)[:40000]
        )
        return store.add_workflow(text.splitlines()[0].lstrip("# ")[:100], text)
    finally:
        await runtime.close()


def load_examples(path: Path, *, require_labels: bool = False) -> list[dict]:
    examples = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not examples:
        raise ValueError("The dataset is empty.")
    if require_labels:
        from .learning_guards import labeled_examples
        examples = labeled_examples(examples)
    for example in examples:
        if not all(k in example for k in ("state", "question", "options", "expected")):
            raise ValueError("Each JSONL example needs state, question, options, and expected.")
        if example["expected"] not in example["options"]:
            raise ValueError("Expected answer must name an option.")
    return examples


async def evaluate(settings: Settings, examples: list[dict], instructions: str, emit) -> dict:
    judge = Judge(settings.model_copy(update={"max_jev_calls": max(settings.max_jev_calls, min(300, len(examples)))}), emit)
    results = []
    try:
        for example in examples:
            answer = (await judge.decide(example["state"], {"answer": {
                "instructions": instructions + "\n" + example["question"], "options": example["options"]}}))["answer"]
            results.append({"expected": example["expected"], "actual": answer["choice"], "correct": answer["choice"] == example["expected"]})
        return {"accuracy": sum(r["correct"] for r in results) / len(results), "examples": len(results), "jev_input_tokens": judge.input_tokens, "results": results}
    finally:
        await judge.close()


def optimize(settings: Settings, train_path: Path, validation_path: Path, component: str, budget: int, emit, *, test_path: Path) -> Path:
    """Explicit, bounded offline optimization. It never executes task tools."""
    try:
        import gepa
    except ImportError as error:
        raise RuntimeError("Install the learning extra first: uv pip install -e '.[learning]'") from error
    from .learning_guards import digest, isolated_splits, reserve_test, save_report
    train, validation, test = [load_examples(path, require_labels=True) for path in (train_path, validation_path, test_path)]
    isolated_splits(train, validation, test)
    run = uuid.uuid4().hex
    defaults = {"gate": GATE_PROMPT, "verify": VERIFY_PROMPT}
    if component not in defaults:
        raise ValueError("Component must be gate or verify.")
    store = Store(settings)
    try:
        initial = store.template(component, defaults[component])
        reserve_test(store.db, run, test)
    finally:
        store.close()
    reflections = 0

    def reflect(prompt: str) -> str:
        nonlocal reflections
        reflections += 1
        if reflections > min(10, settings.max_model_calls):
            raise RuntimeError("Offline generation reflection budget reached; existing prompts remain active.")

        async def call():
            runtime = Runtime(settings, Path.cwd(), emit)
            try:
                return await runtime.complete(prompt)
            finally:
                await runtime.close()
        return asyncio.run(call())

    class Adapter:
        propose_new_texts = None

        def evaluate(self, batch, candidate, capture_traces=False):
            from gepa.core.adapter import EvaluationBatch
            report = asyncio.run(evaluate(settings, list(batch), candidate["instructions"], emit))
            return EvaluationBatch(
                outputs=report["results"], scores=[float(r["correct"]) for r in report["results"]],
                trajectories=[{"example": x, "result": y} for x, y in zip(batch, report["results"])] if capture_traces else None,
            )

        def make_reflective_dataset(self, candidate, eval_batch, components_to_update):
            rows = []
            for trace in eval_batch.trajectories or []:
                rows.append({"Inputs": trace["example"], "Generated Outputs": trace["result"],
                             "Feedback": "Correct" if trace["result"]["correct"] else f"Expected {trace['result']['expected']}; fix the decision boundary."})
            return {key: rows for key in components_to_update}

    result = gepa.optimize(seed_candidate={"instructions": initial}, trainset=train, valset=validation,
                           adapter=Adapter(), reflection_lm=reflect, max_metric_calls=budget,
                           display_progress_bar=False)
    candidate = result.best_candidate["instructions"]
    baseline = asyncio.run(evaluate(settings, validation, initial, emit))
    updated = asyncio.run(evaluate(settings, validation, candidate, emit))
    # The candidate is fixed before either final-test evaluation. Test content
    # and results never reach GEPA selection or reflection.
    test_baseline = asyncio.run(evaluate(settings, test, initial, emit))
    test_updated = asyncio.run(evaluate(settings, test, candidate, emit))
    report = {"component": component, "candidate_hash": digest(candidate), "baseline_hash": digest(initial),
              "split_hashes": {"train": digest(train), "validation": digest(validation), "test": digest(test)},
              "validation_baseline": baseline, "validation_candidate": updated,
              "test_baseline": test_baseline, "test_candidate": test_updated}
    store = Store(settings)
    try:
        save_report(store.db, run, report)
    finally:
        store.close()
    destination = home() / "candidates" / f"{component}-{run}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(destination, json.dumps({"component": component, "instructions": candidate,
        "baseline_accuracy": baseline["accuracy"], "validation_accuracy": updated["accuracy"],
        "codex_reflection_calls": reflections, "evaluation_id": run, "review_required": True}, indent=2))
    return destination
