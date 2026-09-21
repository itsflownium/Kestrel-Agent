# Explicit durable memory

Memory stores user-entered preferences and notes separately from task observations, skill packages, and learned workflow recipes. Kestrel does not silently turn model conclusions into permanent user facts.

In the terminal:

```text
/memory
/memory set global preference response-style "Use concise paragraphs."
/memory set project note build-notes "The project uses the build commands in CONTRIBUTING.md."
/memory forget project build-notes
```

Use the same `set` command to edit an entry. The CLI also supports expiry:

```sh
kestrel memory set build-notes 'Use the documented build commands.' --days 30
kestrel memory set response-style 'Use concise paragraphs.' --kind preference --global
kestrel memory list
kestrel memory forget response-style --global
```

Project scope uses the resolved workspace directory; notes are not shared with sibling workspaces. A project entry overrides a global entry with the same key. Edits increment the revision. Entries record timestamps and explicit-user provenance. Expired entries remain inspectable but are excluded from retrieval. Known credential patterns and configured API-key values are rejected.

Retrieval includes applicable preferences and keyword-relevant notes, bounded to eight entries and approximately 6,000 content/metadata characters. It does not inject the entire library. Notes are historical context, not proof of current files, completed actions, or permission. The current request takes precedence. Relevant memory bypasses the generic fast path so the planner sees it. Memory context is also available during final-response generation, outside the evidence list.

`forget` removes an entry from future retrieval; it does not erase old session logs, previous model requests, backups, or SQLite free pages. An already running task may retain its retrieved snapshot until replanning. Natural-language requests to remember something do not yet write memory automatically; use the explicit commands above. This is lexical retrieval, not semantic/vector search.
