# Repository Agent Instructions

## Matt Pocock Engineering Guardrails

Before making code changes, apply the relevant engineering skill discipline:

- Use `diagnosing-bugs` for bugs, regressions, failing tests, exceptions,
  slowness, or unclear broken behavior. Reproduce first, minimize the case,
  form hypotheses, instrument if needed, then fix and add a regression test.
- Use `tdd` for non-trivial feature work or behavior changes where a test seam
  exists. Prefer red-green-refactor, one vertical slice at a time.
- Use `codebase-design` before changing shared modules, public interfaces,
  cross-cutting behavior, or architecture. Identify the highest useful boundary
  and keep the interface small.
- Use `domain-modeling` when terminology, business rules, state transitions, or
  architectural decisions need to be clarified or recorded.
- Use `prototype` when a throwaway implementation would answer an uncertain
  state-model, logic, or UI design question faster than editing production code.

For very small mechanical edits, apply the same judgment briefly without
stretching the task. For ambiguous or high-impact work, ask only the minimum
questions needed before editing.

User-invoked workflows such as `grill-with-docs`, `to-prd`, `to-issues`,
`triage`, `implement`, `review`, and `ask-matt` should be used when the user
names them or asks for that workflow.

At the start of a new project, repository, or substantial feature, ask once
which workflow to use:

- Recommend `grill-with-docs` when goals, domain language, or boundaries are not
  yet clear.
- Recommend `to-prd` when the conversation already contains enough decisions
  and the next step is a durable specification.
- Recommend `implement` when a PRD, issue, or clear work item already exists and
  the user wants implementation through tests and commit.
- Proceed directly when the user says the task is small, urgent, or fully
  specified.

Do not repeat this workflow gate for every small edit inside the same project
unless the scope changes.

## Supporting Skills

- Use `playwright` when a real browser is needed to verify a user-facing flow.
- Use `security-best-practices` when the user explicitly requests a security
  review, security guidance, or secure-by-default implementation help.
- Use `github:yeet` to publish a completed task through an intentional commit,
  branch push, and pull request.
- Use `github:gh-fix-ci` for failing GitHub Actions checks.
- Use `github:gh-address-comments` for actionable pull-request feedback.

## Agent skills

### Issue tracker

Issues and PRDs live in GitHub Issues. External pull requests are not a triage
request surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the five canonical workflow labels defined in
`docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. Read the root `CONTEXT.md` and relevant
ADRs under `docs/adr/`. See `docs/agents/domain.md`.
