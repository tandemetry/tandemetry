CREATE TABLE IF NOT EXISTS events
(
    event_id    UUID,
    source      LowCardinality(String),
    repo_id     UInt64,
    repo        String,
    type        LowCardinality(String),
    occurred_at DateTime64(6, 'UTC'),
    payload     String,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (repo_id, type, occurred_at, event_id)
