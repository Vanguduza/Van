---
name: google-development
description: >-
  Uses owner-account Google development workers beneath Hermes. Antigravity is
  the primary complex development worker; Jules is a bounded asynchronous GitHub
  maintenance worker.
---

# Google Development Workers

## Invariant

Hermes owns planning, reconciliation, testing and final acceptance.

## Antigravity

Use for complex bounded development units requiring code reasoning, terminal,
browser or multi-file implementation.

Every A3 task must include target project/repository, Project Truth SHA,
capability grant ID, allowed paths/task scope, acceptance tests and
forbidden/protected surfaces.

Antigravity may not independently rewrite canonical architecture, security policy,
Project Truth or Visual Authority.

When Antigravity is `CAPACITY_LIMITED` / `RATE_LIMITED`, route development via Jules
(if configured) or Hermes Claude/Codex delegates. Surface
`ANTIGRAVITY_CAPACITY_LIMITED` only — do not mark Workspace, Gemini runtime, or
Jules as failed because Antigravity quota is exhausted.

## Jules

Prefer for bounded asynchronous repository work such as dependency updates,
missing tests, mechanical refactors, straightforward bug fixes and documentation
synchronization. Jules output returns to Hermes for review and acceptance.

## Evidence

Retain assigned task contract, worker/provider receipt, branch/commit SHA, test
evidence, diff/acceptance result and provenance pointer. A worker reporting
success is not sufficient evidence by itself.
