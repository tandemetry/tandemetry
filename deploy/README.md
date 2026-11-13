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

## Stop and reset

```bash
dc down        # stop, keep data
dc down -v     # stop and delete all data volumes
```

## Pitfalls

- **Port 5432 already in use** (a local PostgreSQL): set `POSTGRES_HOST_PORT` in `deploy/.env`.
- **Changed passwords have no effect** on existing data: the database reads them only when the
  volume is first created. Run `dc down -v` after editing credentials.
- **Kafka data persists** in the `kafka-data` volume, so topics and messages survive restarts.
- **Connecting to Kafka from the host on 9092 fails**: use `localhost:29092`.
- **Memory**: give Docker Desktop at least 4 GB.
- **`up --wait` errors on `kafka-init`**: update Docker Compose to v2.17 or newer.
