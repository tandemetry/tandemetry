# ADR-003: No LLM in the core

- Status: Accepted
- Date: 2026-10-31

## Context
Customers need reproducible, explainable metrics, low running cost and assurance that their code
is not sent to third parties.

## Decision
Attribution and all metrics are deterministic (rules + SQL). LLM-based features (PR type
classification, revert explanations, narrative reports) are optional, disabled by default and
use the customer's own API key.

## Consequences
- + Reproducible numbers, zero inference cost, no data leaves the customer.
- + Product is unaffected by LLM pricing changes.
- − Some nuance (e.g. IDE-agent detection) is out of reach; documented as a limitation.
