# Docker interruption recovery — 2026-09-22

The previous backend retained cleanup retries only in memory and only attempted removal for timeout/cancellation. A crashed Kestrel worker or disconnected Docker client could leave a container without a durable recovery record.

The backend now records a private per-workspace cleanup receipt before launching, uses an OS ownership lock across the command and cleanup, verifies run-specific Docker labels, and checks the recorded target fingerprint. It attempts cleanup after all client exits. The next process recovers a stale receipt before starting new work. Cleanup remains separate from task success and does not undo workspace effects.

## Validation scope

Tests execute real subprocesses against a simulated Docker CLI with a persistent container-state directory. A worker is killed with SIGKILL, leaving the simulated run and receipt; another executor must remove that run before its next launch. Negative controls preserve receipts and refuse execution for foreign labels, changed target metadata and malformed records. A live owner cannot be displaced. Repeated cancellation during subprocess creation still obtains and reaps the client handle. Ordinary client failure triggers cleanup, and output/exit-code tests remain intact.

This is process-protocol evidence, not Docker isolation or real daemon crash evidence. A read-only check of the installed Docker CLI could fingerprint the configured context, but `docker info` returned exit 1. No image was pulled and no real container was started. Live daemon cancellation, crash cleanup and filesystem/network isolation remain unverified.

Final related regression suite: **85 tests passed in 25.15 seconds**, covering Docker cleanup, general features, detached jobs, readiness, provider setup and provider fault handling. Wheel and source distribution builds passed. The complete project suite was not repeated for this checkpoint. An initial cancellation test had to wait for the actual run rather than the newly added context preflight; the final test exercises cancellation after launch and a separate test covers cancellation during startup.
