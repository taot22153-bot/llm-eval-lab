# Domain Docs

This is a single-context repository. Engineering skills should use the domain
documentation below when exploring, planning, implementing, or reviewing work.

## Before Exploring

- Read the root `CONTEXT.md` for the project glossary and domain boundaries.
- Read the ADRs under `docs/adr/` that affect the area being changed.
- If one of these files does not exist, proceed silently. Create domain
  documentation only when terminology or a decision actually needs recording.

## Use the Project Vocabulary

Use terms exactly as defined in `CONTEXT.md` in issue titles, implementation
plans, APIs, tests, and user-facing text. Avoid synonyms that the glossary marks
as ambiguous or incorrect.

If a required concept is missing, first determine whether the new term is
unnecessary. If it represents a real domain gap, record it through the
`domain-modeling` workflow.

## Respect Architecture Decisions

Do not silently override an existing ADR. If proposed work conflicts with an
ADR, identify the conflict explicitly and either follow the existing decision
or create a new superseding ADR with its rationale.
