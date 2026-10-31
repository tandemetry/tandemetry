---
name: new-adr
description: >
  Create an Architecture Decision Record in docs/adr/ in the project's format.
  Use when a change introduces or reverses an architectural decision (new
  dependency, storage, protocol, deployment model, public API shape), when the
  user says "write an ADR", "record this decision", or /new-adr <title>.
argument-hint: "<short decision title>"
---

# New ADR

1. List `docs/adr/` and take the next number (zero-padded to 3 digits).
2. File name: `docs/adr/NNN-<kebab-case-title>.md`.
3. Use exactly this structure, short and concrete:

```markdown
# ADR-NNN: <Title>

- Status: Proposed | Accepted | Superseded by ADR-XXX
- Date: YYYY-MM-DD

## Context
<The forces: problem, constraints, load, what must be true. 3–6 sentences.>

## Decision
<What we do. One paragraph, imperative.>

## Consequences
- + <benefit>
- − <cost or risk, and how it is mitigated>
- Rejected: <alternative> — <one-line reason>
```

4. New ADRs start as `Proposed`. Only the maintainer marks them `Accepted`.
5. If the ADR replaces an older one, set the old one to `Superseded by ADR-NNN`.
6. Add a one-line link in `docs/architecture.md` if the decision changes a component.
