# Experimental macOS desktop adapter

The optional native adapter exposes `desktop_observe` and `desktop_act` over authenticated localhost MCP. It uses macOS Accessibility for one explicitly configured application bundle ID. It does not control the global mouse/keyboard, launch applications, change OS permissions, inspect other apps, read secure-field values, or provide native screenshots. Existing image inspection can consume screenshots supplied by another authorized connector.

Install the `desktop` extra on macOS. Set `KESTREL_DESKTOP_TOKEN` to a private random URL-safe token of 32–256 characters in both the server and Kestrel client environments. Do not put it in the connection URL or a committed file. Generate a value with a local secret generator such as Python's `secrets.token_urlsafe(32)` and store it using your usual private environment mechanism.

```sh
kestrel desktop-server --app com.apple.TextEdit
kestrel connections add desktop http://127.0.0.1:8932/mcp --bearer-env KESTREL_DESKTOP_TOKEN --read-tool desktop_observe
```

Open the selected app yourself. The process hosting the server needs macOS Accessibility authorization in System Settings. The adapter checks permission and fails without it; it never prompts to grant access automatically. A bearer token authenticates the connection but does not expand the user's task authorization. Normal Kestrel MCP action approvals still apply.

Each observation returns an opaque token and bounded element IDs. Actions re-scan the configured app and require the same process, element, and observed properties. The token is consumed before dispatch, including uncertain failures. Press uses an exposed AXPress action; fill requires a writable AXValue. Disabled or secure controls are refused. A fresh observation follows an action. As with other GUI systems, an app can change between the final check and dispatch; inspect actual outcome before retrying.

Cancellation cannot interrupt an OS Accessibility call. Its serialized worker retains ownership until the call ends, preventing another request from overlapping it. Tree scans are limited by node count, depth, child count, and an elapsed-time check. Truncation is reported; it does not mean hidden targets are absent.

Validation: nine desktop tests cover stale targets, process changes, disabled/secure controls, uncertain-effect replay, cancellation serialization, required token authentication, real loopback MCP calls with a fake app backend, and the real macOS permission-denial path. Combined desktop/general feature checks: 21 passed. **Live app observation and manipulation were not validated**: this process reports Accessibility authorization false. Treat the adapter as experimental until that validation is completed. No superiority claim follows from these contract tests.

Apple API reference: [AXIsProcessTrusted](https://developer.apple.com/documentation/applicationservices/1460720-axisprocesstrusted), [AXUIElementCopyAttributeValue](https://developer.apple.com/documentation/applicationservices/1462085-axuielementcopyattributevalue), [AXUIElementPerformAction](https://developer.apple.com/documentation/applicationservices/1462091-axuielementperformaction).
