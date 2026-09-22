# Provider/controller conformance — 2026-09-22

Previous HTTP tests validated adapters and faults largely through mocked transports. The existing engine smoke returned a greeting without executing a general task. This checkpoint adds actual loopback HTTP requests through both supported API protocols and the real controller/tool path.

## Covered paths

For OpenAI-compatible chat completions and Anthropic messages, a scripted HTTP server supplies a typed plan to read a UTF-8 source, request transformed content from the selected API provider, write the artifact through controller-owned permissions, and verify an exact file completion contract. It also supplies bounded review decisions. Tests independently reopen the output and check unchanged input and workspace scope.

The server validates the selected model ID, protocol route and authentication headers, and confirms that no native tool definitions are sent to the generator. Generation and decision token accounting are checked separately. Codex startup is instrumented to fail the test if called; Jev construction likewise fails. Direct MCP discovery follows its real empty-configuration path rather than being replaced with a fake catalog.

| Scenario | Required outcome, exercised on both protocols |
| --- | --- |
| Correct transformed content | Exact artifact and `SAVED`; two generation requests, one decision request; no Codex startup or Jev calls |
| Incorrect generated content | Deterministic file check fails despite the scripted model's affirmative review; task requests input instead of claiming success |
| User denies write | No output file; affirmative model review cannot override permission denial or the failed file check |
| Provider emits native tool request | Response is rejected; no artifact or controller effect is produced |

All **8 cases passed in 67.16 seconds**. These tests establish protocol/controller conformance with scripted responses, not actual provider availability, model reasoning quality, vendor feature compatibility, or latency. The fixture keys and model IDs are dummy values; all traffic is loopback. Shell execution is disabled, so this checkpoint does not claim that an API provider changes the selected execution backend or provides a shell sandbox.

The complete accumulated suite passed **584 tests in 616.44 seconds (10m 16s)**, including the recent review-context and Docker-recovery changes, real isolated Chromium, MCP, terminal UI, workflow and provider tests. The command and raw pytest summary are retained in `validation-provider-checkpoint.txt`. No production code changed in this conformance checkpoint; distribution builds passed at the preceding Docker-recovery checkpoint. Real external-provider credentials and model-specific conformance, live Docker isolation, and native desktop actions remain separate open gates.
