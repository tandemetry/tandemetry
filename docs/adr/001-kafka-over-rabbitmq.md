# ADR-001: Kafka as the event backbone (not RabbitMQ)

- Status: Accepted
- Date: 2026-10-31

## Context
Events arrive from webhooks, historical backfill and optional OTel telemetry. Attribution rules
will evolve, so historical events must be re-processable. Several independent consumers
(attribution, metrics writer, alerts) read the same stream. Backfill creates bursts.

## Decision
Use Kafka (KRaft mode) with topics `raw.github`, `events.normalized`, `events.attributed`.

## Consequences
- + Replay from offsets: re-run attribution after rule changes.
- + Multiple consumer groups on one stream; autoscaling by consumer lag (KEDA).
- + Partitioning by repository keeps per-repo ordering.
- − Heavier to operate than RabbitMQ; mitigated by a single-node KRaft setup in docker compose.
- RabbitMQ was rejected: good for task queues, but no native replay/log retention.
