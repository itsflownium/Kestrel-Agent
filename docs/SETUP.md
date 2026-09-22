# Setup and terminal interface

Run `kestrel setup` or `/setup` inside the terminal. The interview configures the provider, endpoint, model, reasoning effort, optional Jev mode, command execution backend, file access, network, and shell confirmations. Settings are collected before saving, so cancelling the interview leaves the previous settings intact. Provider and Jev keys use separate hidden prompts after saving. Codex OAuth uses `kestrel auth login`.

The welcome panel shows the model, mode, execution backend, permissions, and skill count. `/help QUERY` filters commands. `/details on` shows detailed model, decision, plan, and tool activity; `/details off` keeps the transcript compact. `/tools` shows built-in capabilities and connected tools. Ctrl+C stops active work and quits when idle.

## Docker execution

Select `docker` during setup, or set `execution_backend` and `docker_image` in configuration. Docker must be running and the image must already be present. Kestrel does not pull images, install Docker, or fall back to host execution when Docker fails.

Each shell action runs in a temporary container. Only the workspace is mounted at `/workspace`; file tools continue to use host paths. Use container paths in command arguments. Workspace writes persist; other container files do not. The root filesystem is read-only, `/tmp` is temporary, Linux capabilities are dropped, and CPU, memory, and process counts are bounded. Network follows the selected setting. Read-only access mounts the workspace read-only. Even full access does not add other host mounts. Provider credentials and the Docker socket are not passed into the container. Files already inside the workspace remain accessible to commands, so select the workspace deliberately.

Docker isolates shell commands only. Model API calls, file tools, and connected services retain their own permission boundaries. Images must contain required tools. Desktop/browser connectors run wherever their servers are configured; selecting Docker does not containerize them. Storage occupied by Docker images is outside Kestrel's managed-storage counter.

## Validation status

The initial setup implementation was published while testing was deferred. Subsequent setup, provider, Docker process, UI and full regression results are recorded in FEATURE-VALIDATION.md. Live Docker execution remains unverified because the configured daemon is unavailable; process-fixture tests do not substitute for a real container run.

## Readiness diagnostics

Run `kestrel doctor` or `/doctor` for local configuration/dependency checks. Credential presence is distinguished from authenticated access, missing Jev credentials are not a problem in standard mode, and an installed package is not reported as a working runtime.

Use `kestrel doctor --runtime-checks` or `/doctor runtime` to check the selected Docker daemon and image and briefly launch/close isolated headless Chromium. Docker probes can contact the configured Docker context, including a remote context. They query metadata only: no containers, pulls, installs or page navigation. Docker probes time out after five seconds and kill/reap the probe process; Chromium checks are bounded to twenty seconds. Diagnostics do not display raw subprocess output.

`kestrel doctor --online` separately checks the selected provider's authentication/model-list endpoint and Jev when that mode is selected. It does not generate an answer or establish model quality, vision support or compatibility with every task.

On macOS, the local check reads the current process's Accessibility authorization flag without prompting, changing permissions or inspecting an app. A separately launched desktop-server can have different authorization. Run diagnostics in the environment that will host the server. The native adapter remains experimental until live app validation is completed. A ready browser/daemon check likewise establishes availability only, not end-to-end task success or external connector health.

## Live window resizing

The welcome dashboard is now part of the live prompt render, so it reflows when the terminal changes size before the first message. Fullscreen width is no longer capped at 116 columns. Below 34 rows, a compact header leaves room for input. Response and tool panels use the available terminal width. `/clear` returns to the responsive welcome view. Previously printed transcript lines remain terminal scrollback; Kestrel does not reconstruct historical output on resize.

### Interrupted Docker commands

On timeout or cancellation, Kestrel removes its named container and reaps the Docker CLI process. A failed removal is not treated as success: Kestrel asks Docker to confirm the exact container name is absent. If the daemon is unavailable or the container remains, the error includes its name and the runtime retains it for cleanup retry. Further commands cannot start while that cleanup remains unresolved. Runtime shutdown still closes the other clients and reports cleanup failures.

The retry list exists in the current runtime; after a process crash, use the reported container name to inspect and remove the container through Docker. This is not durable crash recovery. Process-level tests cover cancellation, timeout, cleanup refusal, already-removed containers, and bounded output. Actual isolation and daemon behavior still require live Docker validation; the development machine's configured Colima socket was absent during this update.
