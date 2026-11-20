# Local stack

Single-node Kafka (KRaft), ClickHouse and PostgreSQL 17 for local development.
Requires Docker with Compose v2.17 or newer.

This stack is infrastructure only. During development run the application on the host
(`uv run …`) against these services; a Dockerfile and application services (compose profile
`app`) are added with the first runnable service, see the roadmap.

## Start

```bash
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml --env-file deploy/.env up -d --wait
```

`docker compose ps -a` should show `kafka`, `clickhouse` and `postgres` as healthy and
`kafka-init` as exited (0): it only creates the topics and stops.

## Services

| Service | Host address | Container address |
| --- | --- | --- |
| Kafka | `localhost:29092` | `kafka:9092` |
| ClickHouse HTTP / native | `localhost:8123` / `localhost:9000` | `clickhouse:8123` / `clickhouse:9000` |
| PostgreSQL | `localhost:5432` (`POSTGRES_HOST_PORT`) | `postgres:5432` |

All ports are bound to `127.0.0.1`. Credentials come from `deploy/.env`.

Kafka has two listeners. Containers use `kafka:9092`; clients on your machine must use
`localhost:29092`, because the broker advertises that address to host clients.
Topics `raw.github`, `events.normalized` and `events.attributed` are created with
`KAFKA_TOPIC_PARTITIONS` partitions (default 3, replication factor 1).

## Verify

```bash
alias dc='docker compose -f deploy/docker-compose.yml --env-file deploy/.env'

dc exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
echo hello | dc exec -T kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server kafka:9092 --topic smoke.test
dc exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic smoke.test --from-beginning --max-messages 1

curl localhost:8123/ping
dc exec clickhouse sh -c \
  'clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" -q "SHOW DATABASES"'

dc exec postgres pg_isready -U tandemetry -d tandemetry
dc exec postgres psql -U tandemetry -d tandemetry -c 'select version()'
```

The ClickHouse and PostgreSQL examples read credentials from the containers' environment; pass
your own `POSTGRES_USER` / `POSTGRES_DB` values from `deploy/.env` if you changed them.

## Run the application against the stack

The application reads `TANDEMETRY_*` variables; nested settings use `__`
(`TANDEMETRY_CLICKHOUSE__HOST`, default `localhost:8123`). Reuse the credentials from `deploy/.env`:

```bash
set -a; source deploy/.env; set +a
export TANDEMETRY_CLICKHOUSE__USERNAME="$CLICKHOUSE_USER" \
       TANDEMETRY_CLICKHOUSE__PASSWORD="$CLICKHOUSE_PASSWORD" \
       TANDEMETRY_CLICKHOUSE__DATABASE="$CLICKHOUSE_DB"

uv run tandemetry migrate     # applied: 0001_events.sql (safe to repeat)
dc exec clickhouse sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" -d "$CLICKHOUSE_DB" -q "SHOW CREATE TABLE events"'
```

`events` is a `ReplacingMergeTree`: a redelivered event is removed on a background merge, so
queries that must not double-count use `FINAL` (`SELECT count() FROM events FINAL`).

## Publish a sample event

`tandemetry publish-sample` sends one fixed event to `events.normalized` (Kafka on
`localhost:29092`, override with `TANDEMETRY_KAFKA__BOOTSTRAP_SERVERS`). The key is the
repository id, so all events of a repository land in one partition and keep their order.

```bash
uv run tandemetry publish-sample      # published f9976cac-… to events.normalized
dc exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic events.normalized --from-beginning --max-messages 1 \
  --formatter-property print.key=true --formatter-property print.partition=true
dc exec kafka /opt/kafka/bin/kafka-get-offsets.sh --bootstrap-server kafka:9092 \
  --topic events.normalized         # events.normalized:<partition>:<message count>
```

Running the command twice stores two messages with the same `event_id`; the ClickHouse sink
keeps one row (see `events` above).

## Consume into ClickHouse

`tandemetry consume` moves events from `events.normalized` into the `events` table until Ctrl+C.
With the ClickHouse variables from "Run the application against the stack" exported:

```bash
uv run tandemetry migrate
uv run tandemetry consume             # terminal 1: consuming events.normalized as tandemetry-clickhouse

uv run tandemetry publish-sample      # terminal 2, twice
uv run tandemetry publish-sample
dc exec clickhouse sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" -d "$CLICKHOUSE_DB" -q "SELECT count() FROM events FINAL"'   # 1
dc exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group tandemetry-clickhouse          # LAG 0 on every partition
```

Replay everything (redelivery): stop `consume` with Ctrl+C, reset the group, start it again;
the count stays the same.

```bash
dc exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --group tandemetry-clickhouse --topic events.normalized --reset-offsets --to-earliest --execute
```

A reset is rejected while a consumer is running; after a hard kill wait about 10 s (the
consumer's session timeout) for the group to become empty.

## Stop and reset

```bash
dc down        # stop, keep data
dc down -v     # stop and delete all data volumes
```

## Pitfalls

- **Port 5432 already in use** (a local PostgreSQL): set `POSTGRES_HOST_PORT` in `deploy/.env`
  to a free port, e.g. `15432` (installers often take 5433 for a second version). Variables
  exported in your shell override `deploy/.env`, so after `source deploy/.env` re-source it or
  `unset POSTGRES_HOST_PORT` once you edit the file.
- **Changed passwords have no effect** on existing data: the database reads them only when the
  volume is first created. Run `dc down -v` after editing credentials.
- **Kafka data persists** in the `kafka-data` volume, so topics and messages survive restarts.
- **Connecting to Kafka from the host on 9092 fails**: use `localhost:29092`.
- **Memory**: give Docker Desktop at least 4 GB.
- **`up --wait` errors on `kafka-init`**: update Docker Compose to v2.17 or newer.
