# Prashna Remediation Plan Assessment

Supersession Note: this report is historical. On 2026-07-20, `plan.md` was
revised again for Sarathi 0.3.2 terminology and checker expectations. The
current plan is a one-PR implementation plan and its draft checker passed
20/20. Run a fresh `/plan-assess` after human approval if a formal assessment
gate is needed.

Assessed At: 2026-07-03T18:17:38Z

Assessment Type: `/plan-assess`

Scope: slice/change remediation delta

Verdict: Pass-with-fixes

## Independence Note

This assessment is degraded and non-independent. The host has subagent
capability, but the current delegation policy requires explicit user permission
before spawning subagents. Mechanical verification and qualitative review were
kept separate in this local pass.

## Verification 0: Upstream Consistency

Result: Pass.

- `check_spec.py spec.md --json`: passed 16/16.
- `check_design.py design.md --spec spec.md --json`: passed 13/13.
- `check_spec.py spec.md --require-approvals --json`: passed 17/17.
- `check_design.py design.md --spec spec.md --require-approvals --json`:
  passed 14/14.
- `spec.md` hash:
  `ecb2783a713dce158088b29951eeaeb0e46278abc3e14bfc90bc2078e21061b0`.
- `design.md` hash:
  `34351336f9292e478514ce214c80c28e96cd95990a9ecaa57046a6220534848b`.

Upstream qualitative fitness:

- The accepted SRS and design are structurally fit to plan from.
- The known public-bootstrap contradiction is already classified as an
  artifact revision and is owned by `PR-BASELINE-REMEDIATION`.
- The SRS defers mock UI work, so no mock approval blocks this plan.
- Production canary, staging, synthetic monitoring, and live deployment remain
  legitimately deferred for this single-process baseline remediation slice.

No upstream blocker was found.

## Verification A: Mechanical Plan Check

Result: Pass.

Command:

```bash
python3 /home/sankar/.agents/skills/sarathi/checkers/check_plan.py \
  plan.md --spec spec.md --design design.md --require-approvals --json
```

Scorecard:

- Passed gates: 17/17.
- Plan kind: implementation.
- Delivery items: 3 milestones, 8 PRs, 0 child `WORK` items.
- Coverage: FR 100%, UC 100%, NFR 100%, AT 100%, JT 100%, COMP 100%,
  TEST obligation 100%.
- Uncovered IDs: none.
- Orphan refs, duplicates, bad ID format: none.
- Missing LOC estimates: none.
- Large PRs over the advisory target: none.
- Missing Red/Green TDD text: none.
- Forward dependencies: none.
- Vague hits: 0.
- Approval gates: current `spec.md` and `design.md` approvals are hash-current.
- External-double note: checker saw the "mock UI" wording, and mitigation is
  present because the plan states the accepted spec deferred mock UI work.

Artifact companion check:

- `plan.html` matches `plan.md` on PR inventory, dependency edges, wave order,
  remediation gaps, and the review gate.
- `plan.html` hash:
  `d0f7b8374030a12a32bb0dfa20562bf40b367aca130ad6bd6fc04ef1e1326532`.
- `plan.md` hash:
  `e468b7140b20c083d742e60e70319ec9a5599f1544e1548f83c0bc00594d0e7a`.

## Verification B: Qualitative Scorecard

- PR reviewability: 5/5.
  Fix: keep `PR-BASELINE-REMEDIATION` strict about safe logging only; do not add
  dashboard or telemetry expansion into that PR.
- Plan type and readiness fit: 5/5.
  Fix: after approval, record `plan.approved` before `/code-create`.
- Scope-specific completeness: 4/5.
  Fix: in `PR-BASELINE-REMEDIATION`, mark which obligations are already covered
  by existing tests versus newly implemented by remediation PRs.
- TDD discipline: 4/5.
  Fix: during implementation, make each Red step fail for the named missing
  obligation before adding Green code or test metadata.
- Coverage: 4/5.
  Fix: avoid treating broad requirement mentions in the coverage map as proof;
  use the traceability file to attach concrete tests or accepted residual risk.
- Test-level allocation: 5/5.
  Fix: keep browser, API, docs-contract, subprocess, and compose checks near
  the PRs that own the protected behavior.
- Test-environment allocation: 4/5.
  Fix: make Docker-unavailable behavior explicit in
  `PR-BASELINE-REMEDIATION` results.
- Context-driven review/test allocation: 4/5.
  Fix: preserve explicit security, privacy, accessibility, resilience, and
  deployment review notes in the PR descriptions.
- Inner-test discovery guidance: 4/5.
  Fix: let implementation-local tests add coverage, but do not let them replace
  required `AT`, `JT`, or `TEST` mappings.
- Verification-oracle allocation: 5/5.
  Fix: keep the stated observable oracles in the final PR descriptions.
- Contract-fixture allocation: 4/5.
  Fix: ensure `PR-BASELINE-REMEDIATION` names the actual socket-close mechanism
  once selected.
- External double verification allocation: 5/5.
  Fix: keep GitHub OAuth outside this remediation unless a behavior change
  touches it.
- UX/presentation allocation: 4/5.
  Fix: make `PR-BASELINE-REMEDIATION` assert no horizontal overflow or content
  overlap at 360 px, not merely successful clicks.
- Mock UI approval: 5/5.
  Fix: none; current upstream artifacts defer mock UI work.
- Logging/error-handling allocation: 4/5.
  Fix: add a redaction test that would fail on passwords, tokens, moderator
  keys, uploaded bytes, and participant contact details in logs.
- Build/deployment allocation: 4/5.
  Fix: include cleanup, skip/manual gate, and residual-risk wording when Docker
  is unavailable.
- Documentation allocation: 4/5.
  Fix: keep README, deploy runbook, and traceability updates tied to the PRs
  that change or verify behavior.
- Planned Touch Sets: 4/5.
  Fix: if implementation needs files outside a touch set, stop and revise the
  plan or explain the scope exception before editing.
- Sequencing: 5/5.
  Fix: keep `PR-BASELINE-REMEDIATION` first; later work depends on the clarified
  artifact and traceability structure.
- Parallelism and worktrees: 5/5.
  Fix: use separate worktrees only for the Wave 4 browser/header/mobile PRs.
- Production quality: 4/5.
  Fix: keep live host changes out of scope and use local/CI smoke evidence.
- Shippability: 5/5.
  Fix: each PR should keep all structural checks, pre-commit, and targeted
  tests green before merge.

## Top Fixes

1. In `PR-BASELINE-REMEDIATION`, distinguish existing-test evidence from new
   remediation tests and accepted residual risks.
2. In `PR-BASELINE-REMEDIATION`, revise the approved SRS and refresh the
   approval ledger before later code PRs proceed.
3. In `PR-BASELINE-REMEDIATION`, keep logging narrowly scoped and prove
   redaction of secrets, tokens, moderator keys, uploaded bytes, and contact
   details.
4. In `PR-BASELINE-REMEDIATION`, make Docker-unavailable handling, cleanup, and
   residual risk explicit.

## Verdict

Verdict: Pass-with-fixes.

The plan is fit for human approval and can gate `/code-create` after approval.
The fixes above are execution constraints rather than blockers. The most
important implementation-time guardrail is to avoid traceability theater:
`PR-BASELINE-REMEDIATION` must map every accepted `AT`, `JT`, and design `TEST`
obligation to concrete existing tests, new remediation tests, or explicit
residual risk.
