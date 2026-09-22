# Inspecting retained execution evidence

After a tool call returns or fails, Kestrel stores its result and a separate redacted invocation record. An observation's `evidence_id` retrieves the result. Its `invocation_evidence_id` retrieves the attempted tool arguments, action/tool identity, status, whether the executor was called and returned, and a link to the result. These records are scoped to the session and survive restart.

Use `read_evidence` with either ID and follow its character offsets for large records. `search_evidence` can find text in both types of record. An invocation documents an attempt, not successful execution: inspect its status and result. Executor flags describe Kestrel's tool-dispatch boundary, not proof that every downstream OS or remote action occurred. Interrupted in-flight effects continue to use the existing uncertainty/retry controls; this post-call record does not replace them.

Compact context includes invocation IDs, argument lengths and truncation flags. It uses spare excerpt space for arguments when a result is short, avoiding a fixed 500-character cutoff that could hide the end of a verification command. Older sessions without invocation records are labeled accordingly; Kestrel does not invent evidence for them. The normal storage limit and credential redaction still apply.

Completion checks remain in the controller ledger across repairs. A new plan can omit an existing check without erasing its verdict. To rebind a result check, its reference must name an action declared in the new plan; references to absent old actions remain invalid. Failed retained checks still block completion. Retrieve missing historical evidence before deciding whether another external action is needed.
