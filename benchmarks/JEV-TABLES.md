# Jev-driven table queries — September 20, 2026

The previous controller still spent 16–22 seconds planning simple table aggregations. The new bounded path uses Jev to select a query from the observed schema, deterministic Decimal computation to execute it, and an independent Jev check of the query and answer. Supported tasks need zero generation calls. It is a generic schema-driven capability, not a benchmark lookup.

## Repeated comparisons

Each table task ran three times per arm on identical isolated fixtures with fresh sessions. The generation model configuration remained GPT-6-Astra, medium, in both arms; Kestrel's supported path never invoked it. Arm order alternated, and the repeated block ran after the first comparison. Model API caching, service variability, and warm runtimes are not controlled. These are small repeated engineering trials, not population-level estimates.

| Task | Kestrel median | Direct Codex median | Median ratio | Checks passed |
| --- | ---: | ---: | ---: | --- |
| Filtered CSV sums | 2.600 s | 8.455 s | 3.25× faster | 3/3 each |
| JSON means with two filters and invalid values | 2.678 s | 8.555 s | 3.19× faster | 3/3 each |
| CSV counts with categorical/numeric filters | 2.722 s | 20.503 s | 7.53× faster | 3/3 each |

Every Kestrel table run used three Jev calls and zero generation calls. Both arms returned correct numeric mappings, preserved the input files, and passed the file-scope checks. Quality matched on these checks; broader superiority and dollar-cost savings are not established.

The multi-file policy regression remained on the general path and passed for both arms: Kestrel 25.137 s versus Codex 13.964 s. That remaining loss is part of the result, not excluded from the broader picture.

The required-write boundary test also passed for both agents: the shortcut was not used, and totals.json contained the expected numeric totals before SAVED was returned. Kestrel took 51.506 s versus Codex 21.672 s, using four generation calls and eight Jev calls. Its plan unnecessarily generated a JSON serialization already available from the table tool, highlighting further general-path overhead.

## Boundaries and validation

The recipe accepts one explicitly named CSV/JSON file, at most 12 KB and 64 records, with at most 16 common columns. Jev chooses sum/mean/count/min/max, source-derived grouping/value columns, and up to three AND predicates from at most 64 choices. Categorical choices must literally occur in the request and source; numeric thresholds come from the request. Unsupported semantics and output formats use the general agent. Permission checks still apply, and a changed source hash prevents shortcut completion.

62 offline tests pass. The new tests cover dynamic columns/predicates, limits, decimal output, unsupported requests, independent-check rejection, and source changes. An early test caught a numeric threshold followed by sentence punctuation; it was fixed before the completed live trials. The initial interrupted run's one completed baseline record is retained separately and excluded from performance comparisons.

Artifacts:

- `results-jev-tables.json`: first complete table/multi-file comparison.
- `results-jev-tables-repeated.json`: two additional trials of each table task.
- `results-jev-tables-interrupted.json`: interrupted pre-fix run, not performance evidence.
- `results-jev-tables-write.json`: required-write boundary test.

Source hashes match the final application source in all completed comparisons. Raw answers, input fixtures, tool events, Jev choices, and output files are retained. The numeric graders were additionally tightened to reject booleans; inspected saved outputs contain actual numbers and also pass that stricter check.

Reproduce with:

```sh
python benchmarks/workloads.py --tasks csv_totals,table_mean_variant,table_count_variant --repeat 3 --output benchmarks/results-jev-tables-repeated.json
python benchmarks/workloads.py --tasks table_write_variant --output benchmarks/results-jev-tables-write.json
```

These commands consume live provider usage. Use a new output path to preserve earlier trials. The next priority remains general-task planning and recovery overhead; adding Jev indiscriminately does not make every task faster.
