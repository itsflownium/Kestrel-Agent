# Connected general-purpose tools

Kestrel can connect directly to Streamable HTTP MCP servers with any supported model provider. Configure an already installed, trusted server:

```sh
kestrel connections add browser http://localhost:8931/mcp
kestrel connections add service https://example.com/mcp --bearer-env SERVICE_MCP_TOKEN
kestrel connections list
kestrel connections remove service
```

Inside the agent, use `/connections add NAME URL [BEARER_ENV]`, `/connections remove NAME`, and `/tools`. Configuration itself does not contact the endpoint. Discovery happens when planning or using `/tools`. Only explicitly configured endpoints are used. No server is installed or started automatically. Bearer tokens are read from the named environment variable, never from URLs or model arguments.

Direct servers appear as `direct:NAME`. Their exact advertised tool schemas are checked before dispatch. Existing Codex-connected tools remain available with Codex. Direct connections are independent of both the generation provider and the shell execution backend. Tool actions retain Kestrel's existing permission prompts and uncertain-effect receipts. Localhost HTTP is allowed; other servers require HTTPS. Network-disabled and read-only profiles cannot execute connected tools. Configured servers control their own isolation and account access; Docker mode applies only to shell actions.

The `/browser-workflow` skill describes observe–act–verify behavior for browser and desktop tools. Accessibility/DOM-based tools can provide useful observations to the current text controller. Image/audio blocks are marked unavailable to the model rather than presented as understood content. A vision-capable controller, native desktop adapter, stale-target enforcement, and broad computer-use evaluation remain future work. This update is not a claim of complete visual computer-use capability.

Implementation uses the official [MCP Python SDK client](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/client.md), with a `<2` compatibility bound. One worker owns each persistent session and its shutdown. Cancellation closes the connection without replaying the action. A disconnected or timed-out remote call can have an unknown external effect; it is not safe to assume rollback.

Tests and live connector execution are deferred at the user's request. Dependencies were installed; no server was contacted to validate this implementation.
