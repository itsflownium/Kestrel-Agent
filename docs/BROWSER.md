# Isolated browser tools

Install the optional browser runtime, then start the local adapter in another terminal:

```sh
uv pip install -e '.[browser]'
python -m playwright install chromium
kestrel browser-server
```

Register it once:

```sh
kestrel connections add browser http://127.0.0.1:8931/mcp --read-tool browser_tabs --read-tool browser_snapshot --read-tool browser_screenshot
```

Then use `/tools` and `/browser-workflow your task` inside Kestrel. Browser commands go through the existing MCP permission prompts. The adapter can serve any supported generation provider. `--headless` hides its browser; `--port` selects a different localhost port. Stopping the server closes its isolated browser.

The server exposes `browser_open`, `browser_tabs`, `browser_snapshot`, `browser_screenshot`, and `browser_act`. Open/snapshot return page text, visible elements across frames, frame and target IDs, and an observation token. Click, fill, select, or a supported keypress requires a target from the current observation. A frame attachment, navigation, removal, consumed observation, detached element, changed label/type/href, or hidden target forces another inspection. Actions return a new snapshot so success can be checked against visible state. A timed-out action may have taken effect; inspect rather than repeat it blindly.

No arbitrary JavaScript, invented selectors, uploads, downloads, or access to the user's existing browser profiles is exposed. Browser downloads are disabled; the context has no preexisting login state. Users may sign in manually within that isolated browser when a task needs an account. Browser runtime files occupy additional disk space outside Kestrel's managed storage counter.

This is a local trusted-client server, bound to 127.0.0.1, not an authenticated multi-user service. Do not expose its port to a network or connect untrusted clients. Tool approval and task authorization are enforced by Kestrel; another client connecting directly does not inherit those checks. Browser network access is that of the server, not the Docker shell backend.

Actions operate on visible DOM targets. Viewport screenshots can be interpreted through `inspect_image` with a vision-capable model, as described below. The browser adapter does not automate canvas-only interfaces, control native desktop applications, handle file pickers, or implement robust multi-step login flows. Stale-target checks reduce mistakes but cannot make browser inspection and an eventual click atomic; dynamic pages may still change between them.

### Viewport images

`browser_screenshot(tab)` returns a viewport PNG alongside a refreshed DOM observation across frames. The normal direct-MCP connection retains the pixels in Kestrel's bounded image cache and exposes an image_id for `inspect_image`. This joins the browser adapter to the image-input support in VISION.md; no personal browser profile or desktop capture is used.

DOM state and pixels are captured sequentially, not as an atomic page transaction. Refresh after UI changes, and continue using observed DOM targets for actions. Screenshot coordinates are not desktop coordinates; coordinate-based canvas/desktop actions are not implemented by this tool.

Real browser and MCP tests verify the viewport image, image-ID cache retrieval, and subsequent fill/click/verification through the fresh DOM observation. Seven focused browser/vision tests pass after updating the catalog assertion for the fifth browser tool. The preceding full-suite run passed 324 tests before this screenshot addition.

### Embedded frames

Snapshots inspect up to 20 frames, expose 150 targets and 16,000 characters of text in total, and report truncation. Each target names its frame; frame metadata records its URL and name. Nested and cross-origin frames use [Playwright frame APIs](https://playwright.dev/python/docs/api/class-frame). Hidden ancestor frames suppress their content and actions. Any frame attachment, navigation or removal invalidates the observation.

Frame-tree changes during collection discard partial observations and allow up to three read-only collection attempts, each bounded to 20 seconds. Actions are never replayed by this retry. Dynamic pages may still fail to settle; inspect again rather than guessing targets. Real Chromium tests cover nested cross-origin fill/save/verification, navigation/removal invalidation, hidden ancestors, and frame/target limits.

For an existing connection, use `/connections reads browser browser_tabs browser_snapshot browser_screenshot`. This explicitly identifies trusted observation operations so verification can refresh them and repairs do not reuse stale results. Normal approvals and network/access checks remain. Do not list `browser_open` or `browser_act`: they change browser state. Omit tools after `/connections reads browser` to clear the declarations. Server-provided annotations never enable this setting automatically.
