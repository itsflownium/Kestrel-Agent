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

The `/browser-workflow` skill describes observe–act–verify behavior. Image blocks are validated and cached for `inspect_image` with a vision-capable model; audio inspection remains unavailable. The isolated browser adapter supports DOM targets, frames and stable screenshot-guided canvas clicks. The app-scoped native macOS Accessibility adapter is experimental and still needs live permissioned validation. These adapters do not establish broad computer-use reliability.

Implementation uses the official [MCP Python SDK client](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/client.md), with a `<2` compatibility bound. One worker owns each persistent session and its shutdown. Cancellation closes the connection without replaying the action. A disconnected or timed-out remote call can have an unknown external effect; it is not safe to assume rollback.

Real loopback MCP tests cover catalog discovery, schema validation, calls, persistent sessions, image caching and cleanup. Live browser fixtures exercise the same transport; this does not establish compatibility with every external service.

## Large catalogs and tool discovery

The planner receives a complete JSON preview bounded to 12,000 characters, with counts of omitted tools and discovery errors. Small definitions include their full input/output schemas. Oversized entries carry metadata and `definition_complete=false`; the preview never cuts a schema or JSON document halfway through.

`discover_tools(query, server, offset, limit)` searches all connected tool names and full descriptions, including entries omitted from the prompt. Query terms are case-insensitive and all must match; server is an optional exact-name filter. Pages include `next_offset`. Discovery descriptions are capped and explicitly labeled when shortened.

`inspect_tool(server, tool)` retrieves a definition before the planner constructs arguments. Complete results expose `definition`, including `inputSchema` and any `outputSchema`. Large definitions return exact JSON text chunks; continue at `next_offset` with the first `definition_sha256` as `expected_sha256`. A changed definition rejects continuation rather than mixing versions. The hash identifies content, not trust or authorization.

Discovery reads a cached catalog snapshot shared with the current planner. `/tools` refreshes the engine catalog; a subsequent plan uses that refreshed snapshot. Server-side argument validation still occurs at dispatch. Discovery never invokes the advertised operation, grants access or bypasses prompts. It is available under read-only permissions when network access is enabled; connected action restrictions remain unchanged. Server descriptions remain untrusted task data.
