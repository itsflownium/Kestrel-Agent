# Exact source evidence and expected failures

File reads now parse and hash one captured byte snapshot. Previously, parsing occurred before a separate final file read for SHA256; an intervening source change could pair older extracted content with a newer hash. The new hash describes the bytes actually parsed, so a later write rejects a changed source. PDF/DOCX/XLSX parsers consume an in-memory snapshot as well. Reads remain bounded to 20 MB and reject substituted final-component symlinks and non-regular files.

Complete small plain-text reads expose `raw_text`, preserving UTF-8 text including CRLF, trailing newlines, tabs, and spaces. Plans can bind this text directly into copies or concatenation while supplying the observed SHA256. Partial reads and document extraction do not expose a full-source `raw_text` field. This avoids asking a model to reproduce source bytes for a mechanical append.

Failure verification now distinguishes successful recovery from an explicitly requested observation of failure without retry. A failed command remains a failed command; the question is whether the user's requested outcome is complete. This does not grant retry permission, remove Jev review, or bypass the original-task completion check.

All 163 offline tests pass. New controls preserve exact CRLF/whitespace through a real write, prevent full-source binding from partial reads, and change a PDF source during extraction to confirm that its observed hash remains attached to the old bytes and an overwrite is rejected.

The live comparison in `results-exact-source.json` uses the strengthened stale-write fixture with an explicit final newline and observed refresh, plus the partial-effect fixture requiring a failed script to run exactly once. These are development regressions, not a held-out superiority study.

| Revised case | Kestrel | Direct Codex | Result |
| --- | ---: | ---: | --- |
| Preserve upstream content and append exact text | 21.651s | 11.385s | Both passed, including final newline and observed refresh |
| Observe partial failure without replay | 20.996s | 10.763s | Both passed; counter remained 1 |

The append used two generation calls instead of the earlier three, with a direct raw-text binding and current hash. The expected-failure case reached final response generation without a recovery replan. These are single paired diagnostic runs; both still lose on latency to direct Codex, and they do not establish broad quality superiority.
