# Background jobs

```sh
kestrel jobs start 'Read the project notes and summarize the open questions' -C /path/to/workspace
kestrel jobs list
kestrel jobs show JOB_ID
kestrel jobs cancel JOB_ID
```

In chat, `/jobs`, `/jobs show ID` and `/jobs cancel ID` inspect or cancel jobs without leaving the current task. Start detached work from the top-level CLI. Each job creates a separate session and snapshots the selected settings. Provider authentication uses the same local credentials as normal Kestrel; no new account login or permission grant is implied. Jobs use standard or Jev mode according to that snapshot.

Workers detach from the launching terminal with standard input closed. Requests, settings snapshots, status and worker logs live in owner-only job files under Kestrel's private storage. Task text is passed through a private file rather than a command-line argument. A parent reaper handles worker exit when the launching process remains alive. Normal model, action, time and storage budgets still apply during execution.

## Ownership and cancellation

An OS file lock establishes worker ownership. The status response includes `worker_owned`; a stored PID or heartbeat alone is never treated as proof that a worker is alive. Cancellation writes a job-specific request marker which the worker observes while running. It then cancels the agent, checkpoints the session and closes its resources. No stored PID is signalled. A cancellation request is not confirmation that cleanup has finished; wait for a terminal status and `worker_owned: false`.

Jobs sharing the same Kestrel home and canonical workspace are serialized by a second ownership lock. A competing background job fails before task execution. These locks coordinate managed background workers only: they are not an OS filesystem sandbox, do not block other applications or foreground sessions, and do not coordinate overlapping parent/child workspace paths. Choose distinct workspaces when running separate jobs concurrently.

Interactive `kestrel resume SESSION` and `/resume SESSION` refuse sessions recorded as owned by a live background worker. Cancel and wait before resuming. If a process exits without a terminal checkpoint, status becomes `lost_worker`. This is not success or proof that an external effect stopped; inspect the saved evidence and normal uncertain-effect protections before continuing. Jobs are never automatically retried. Cancellation is cooperative; a hung worker remains owned until it exits, rather than being falsely reported stopped.

## Permissions and user input

An unattended worker cannot answer approval prompts. The first required approval interrupts the task and produces `needs_approval`, preserving the session for interactive continuation. It does not grant permission, repeatedly retry after denial, or continue making model calls to repair around the missing approval. Configured permissions and tool guards remain in force; configured actions that do not require a prompt can run.

A clarification question produces `needs_input`, not `completed`. Reopen the saved session and use `/steer YOUR ANSWER` to retain the original task and evidence. For a permission wait, reopen the session and `/continue`, then review the normal action request. Current uncertain-effect handling may ask you to inspect an interrupted effect before authorizing a retry.

Statuses are `starting`, `running`, `stopping`, `finishing`, `completed`, `cancelled`, `needs_approval`, `needs_input`, `failed` or the observed `lost_worker`. A terminal result is published after resource cleanup. Cleanup failure is reported as failure even if an answer was produced. Startup without observed ownership remains unconfirmed and is labelled lost after the startup window; a cancellation marker also prevents a delayed worker from starting actions.

This release does not provide scheduled jobs, automatic retries, process migration, live steering of detached workers, notifications, or a distributed queue. Background work is bound to this machine and its logged-in account/runtime availability.

## Evidence

Process-level tests verify locks and cancellation across actual Python processes, cleanup, cancelled-before-start behavior, workspace contention, stale-PID handling and private launch files. Controlled real-engine tests execute file tools and prove that a required approval stops before writing. Other tests cover cleanup failures, clarification state and ownership checks beyond the visible 100-job list.

A live Astra-medium, standard-mode job read a temporary file and returned its random one-line value with no workspace changes. One generation call, one decision call, zero Jev calls; worker wall time 18.204 seconds (agent run 16.86 seconds). Evidence is retained in `benchmarks/results-background-job-smoke.json`. This is one functional smoke test, not a quality, speed or cost comparison against Codex or validation of every external provider/backend.
