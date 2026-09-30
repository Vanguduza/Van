# OWNER DECISION 2026-09-30 — BROWSER AUTOMATION TASK SCOPE (and Programme B authorization recording)

Status: OWNER ANSWERS RECORDED VERBATIM. The integrator's reading of answer A (section 3) is an
INTERPRETATION PENDING OWNER CONFIRMATION. It is not a decision and confers no authority.

Channel: owner answers in Claude Code session `session_01ELKqm4GCPmPvF3ggKkgB1J`, 2026-09-30.
No device, biometric or cryptographic signature is claimed. This is not signed-ingress evidence
(owner decisions 2026-09-29 section 2 keep `SIGNED_INGRESS_PENDING`).

Related records:
- `docs/decisions/OWNER-DECISIONS-20260929-STAGEHAND-PRIVATE-PLANE.md` (sha256
  `64f1c0560ef88776d0d199392d315767ea3576827e335ba2da8081d12e307c81`): sections 7 to 9 are the
  parent authority that answer B cites.
- `docs/project-state/authorizations/auth-20260930-owner-derived-programme-b-browser-deploy.json`
  records answer B.

## 1. Owner answers (verbatim)

A. The browser automation policy question.
   Question put to the owner: "Automated clicks on arbitrary web pages cannot be proven safe by a
   classifier (the page controls every input it reads). Which browser automation policy should
   Programme B adopt?" The options offered were allowlist-only, keep hardening the classifier, and
   read-only until qualified.

   Owner answer (verbatim, spacing and wording preserved):

   > I do not want to build  a fixed allowlist, pages should relevant to the task truth

   sha256 (UTF-8, exact characters between the quotes, no newline):
   `3bab5be4342e18f9ddb84ce612399aa51d7b42b4f368428a531e406760a4ea3c`

B. The authorization recording question.
   Question put to the owner: "Units G–G5 browser/deploy commits were ordered by your §7–§9
   decisions but no VAN authorization record covers those paths. How should that be recorded?"

   Owner answer (verbatim, the selected option label):

   > Record OWNER_DERIVED (Recommended)

   sha256 (UTF-8, exact characters between the quotes, no newline):
   `6a16a0f0bc8718a3aaf84ddefaf8261565916fa39a944e4055eb65b7a12821d3`

## 2. What is decided

- Answer A decides that Programme B does **not** adopt an owner-maintained fixed allowlist, and that
  the pages automation may act on are to be bounded by relevance to the task's truth. The owner has
  not said how "task truth" is established or enforced. Section 3 is a proposed reading of that.
- Answer B decides that the Programme B browser/deploy commits are recorded under `OWNER_DERIVED`
  authority citing the 2026-09-29 decisions sections 7 to 9, with ledger rows for those commits and
  no signature claimed. The record is
  `auth-20260930-owner-derived-programme-b-browser-deploy`.

Neither answer changes the 2026-09-29 decisions. Payments stay out of automation, Jev never
executes, Stagehand never self-certifies or actuates, and owner takeover preempts automation.

## 3. Integrator's interpretation of answer A — PENDING OWNER CONFIRMATION, NOT A DECISION

This is the integrator's reading, recorded so that implementation can be traced to it. It carries
no authority of its own. If the owner confirms, amends or rejects it, that is recorded as a new
append-only decision; this section is not edited to match. Unit G6a is implementing this reading.
Its code is therefore implementation against an unconfirmed interpretation. It must not be
described as implementing an owner decision until the owner confirms the reading.

- No owner-maintained static allowlist of domains, pages or actions.
- Scope is derived per task from the task's own truth: the admitted goal or instruction, the domain
  scope, the admitted action class, and owner approvals already recorded for that browser task (and
  its Hermes mission).
- Automated clicks, fills, selects and key presses may run at the task's admitted class only on
  pages and against targets that are within that task's scope and consistent with its admitted
  goal. Anything outside the task truth goes to lane 4 (owner takeover / policy refusal).
- Existing invariants stay: payments are never automated (payment boundary), Jev never executes,
  Stagehand never self-certifies or actuates (sections 7 and 8), owner takeover preempts (section
  9), and unknowns fail closed.
- The mechanism fixes from review I5 are still required: hit-test at the click point,
  element-instance binding, press_key focus classification, form/submit context, visible text as
  well as accessible name, and empty name → A4. They make "the target" mean the element actually
  acted on, and task-scope enforcement depends on that.

## 4. Source note (verbatim copy)

Below is the integrator's scratch note of the exchange, copied without edits. Its sha256 was
`55bcc330adf5d11f00e638fe01735c188ad6fd5ac68a0a85d8049384e969ce76` when copied.

```text
OWNER DECISION — BROWSER AUTOMATION SCOPE (answer in Claude Code session session_01ELKqm4GCPmPvF3ggKkgB1J, 2026-09-30; no device or cryptographic signature claimed)

Question put to the owner: "Automated clicks on arbitrary web pages cannot be proven safe by a classifier (the page
controls every input it reads). Which browser automation policy should Programme B adopt?" Options offered:
allowlist-only / keep hardening classifier / read-only until qualified.

Owner answer (verbatim): "I do not want to build  a fixed allowlist, pages should relevant to the task truth"

Second question: "Units G–G5 browser/deploy commits were ordered by your §7–§9 decisions but no VAN authorization
record covers those paths. How should that be recorded?"
Owner answer: "Record OWNER_DERIVED (Recommended)" — i.e. append a VAN authorization record citing the owner's
2026-09-29 decisions §7–§9 as authority for backend/van_gateway/browser/**, deploy/van-browser-core/**,
deploy/van-private-core/** plus ledger rows for those commits; no signature claimed.

Integrator's interpretation of the first answer (to be confirmed by the owner, not a new decision):
- No owner-maintained static allowlist of domains/pages/actions.
- Scope is derived per task from the task's own truth: the admitted goal/instruction, domain scope, admitted action
  class, and owner approvals already recorded for that browser task (and its Hermes mission).
- Automated clicks/fills/selects/key presses may run at the task's admitted class only on pages and against targets
  within that task's scope and consistent with its admitted goal; anything outside the task truth goes to lane 4
  (owner takeover / policy refusal).
- Existing invariants stay: payments are never automated (§ payment boundary), Jev never executes, Stagehand never
  self-certifies or actuates (§7/§8), owner takeover preempts (§9), fail-closed on unknowns.
- Mechanism fixes from review I5 (hit-test at click point, element-instance binding, press_key focus
  classification, form/submit context, visible text as well as accessible name, empty-name → A4) remain required:
  they make "the target" mean the element actually acted on, which task-scope enforcement depends on.
```
