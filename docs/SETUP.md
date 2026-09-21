# Setup and terminal interface

Run `kestrel setup` or `/setup` inside the terminal. The interview configures the provider, endpoint, model, reasoning effort, optional Jev mode, command execution backend, file access, network, and shell confirmations. Settings are collected before saving, so cancelling the interview leaves the previous settings intact. Provider and Jev keys use separate hidden prompts after saving. Codex OAuth uses `kestrel auth login`.

The welcome panel shows the model, mode, execution backend, permissions, and skill count. `/help QUERY` filters commands. `/details on` shows detailed model, decision, plan, and tool activity; `/details off` keeps the transcript compact. `/tools` shows built-in capabilities and connected tools. Ctrl+C stops active work and quits when idle.

## Docker execution

Select `docker` during setup, or set `execution_backend` and `docker_image` in configuration. Docker must be running and the image must already be present. Kestrel does not pull images, install Docker, or fall back to host execution when Docker fails.

Each shell action runs in a temporary container. Only the workspace is mounted at `/workspace`; file tools continue to use host paths. Use container paths in command arguments. Workspace writes persist; other container files do not. The root filesystem is read-only, `/tmp` is temporary, Linux capabilities are dropped, and CPU, memory, and process counts are bounded. Network follows the selected setting. Read-only access mounts the workspace read-only. Even full access does not add other host mounts. Provider credentials and the Docker socket are not passed into the container. Files already inside the workspace remain accessible to commands, so select the workspace deliberately.

Docker isolates shell commands only. Model API calls, file tools, and connected services retain their own permission boundaries. Images must contain required tools. Desktop/browser connectors run wherever their servers are configured; selecting Docker does not containerize them. Storage occupied by Docker images is outside Kestrel's managed-storage counter.

## Validation status

Implementation is untested at the user's request to defer tests. The Docker CLI exists on the development machine, but its configured daemon socket was absent. No container run or UI regression suite was performed for this update.

## Live window resizing

The welcome dashboard is now part of the live prompt render, so it reflows when the terminal changes size before the first message. Fullscreen width is no longer capped at 116 columns. Below 34 rows, a compact header leaves room for input. Response and tool panels use the available terminal width. `/clear` returns to the responsive welcome view. Previously printed transcript lines remain terminal scrollback; Kestrel does not reconstruct historical output on resize.
