# Task-specific execution on a shared controller

Kestrel uses one provider-neutral controller, with task-specific tools and skill procedures. Jev is an optional decision component; it does not replace generation, execute tools, grant permissions, or provide evidence by itself.

```mermaid
flowchart TD
    U[Terminal request and selected skills] --> P[Configured model: plan and generate]
    M[Explicit scoped memory] --> P
    S[Skill metadata, then selected guidance] --> P
    P --> V[Typed plan and dependency validation]
    V --> C[Controller: permission, budget, scheduling]
    J[Standard or Jev decisions] --> C
    C --> Code[Coding: inspect, hash-checked edit, focused checks]
    C --> Browser[Browser: observe, act on current target, observe]
    C --> Data[Documents and data: inspect, transform, reopen]
    C --> Workflow[Workflow: validate inputs, bind parameters, execute graph]
    Code --> E[Evidence and effect receipts]
    Browser --> E
    Data --> E
    Workflow --> E
    E --> Check[Exact completion checks and semantic review]
    Check -->|Incomplete| R[Repair affected actions; reconcile uncertain effects]
    R --> P
    Check -->|Supported outcome| A[Answer with evidence and limitations]
```

## Existing enforcement and limits

| Path | Enforced mechanism | Remaining gap |
| --- | --- | --- |
| Shared controller | Typed tool arguments, permissions, bounded plans and model usage, durable observations, completion contracts, uncertain-effect reconciliation | Broad held-out comparisons; more provider conformance coverage |
| Coding | Source hashes for overwrites, dependency references, command receipts and exact artifact/result checks | The planner must choose useful tests; a zero exit code alone cannot establish task quality |
| Browser | Isolated browser context, observation tokens, current-target validation, token consumption before effects, new snapshot after action | Main-frame DOM only; no native desktop vision, iframe/canvas or authenticated personal-session coverage |
| Documents/data | Typed table and file tools, bounded reads, hash-aware writes, artifact checks | Rendering and deeper semantic checks depend on available tools and the chosen plan |
| Workflows | Typed template inputs, structured substitution, dependency validation, normal permission/evidence path | Behavioral certification and promotion on unseen parameters are still pending |
| Skills | Local provenance, bounded discovery, prerequisite reporting, on-demand guidance, explicit invocation | Guidance is not executable enforcement; format validation is not a quality benchmark |

Task-specific procedures live in focused skills rather than a growing universal prompt. The skill library is a discovery interface; opening a preview does not execute its instructions. Local and external content remain evidence, not authority to change the user's task.

## Next architecture gates

1. Evaluate a short observe/act/check loop against the current plan graph on dynamic browser tasks, using identical models and tool adapters. Adopt it only if repeated independent outcomes support the change.
2. Add native desktop/vision through a real adapter and a model transport that preserves images. A text-only model must not receive a claim that it saw an image.
3. Certify workflow/skill revisions using isolated fixtures, unseen inputs, and effect-state oracles before describing them as reliable reusable automation.
4. Compare quality on coding, browser, research, documents/data, and recovery separately. Preserve failures and tool-setup exclusions. No architecture or skill count proves superiority over another agent.
