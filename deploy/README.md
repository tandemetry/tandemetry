# Local stack

Single-node Kafka (KRaft), ClickHouse and PostgreSQL 17 for local development.
Requires Docker with Compose v2.17 or newer.

This stack is infrastructure only. During development run the application on the host
(`uv run …`) against these services; a Dockerfile and application services (compose profile
`app`) are the next roadmap item.

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

## Receive GitHub webhooks

Needs a GitHub App installed on the repositories and `~/.tandemetry.env`, see
[docs/github-app.md](../docs/github-app.md). A session uses four terminals, each started from the
repository root:

| Terminal | Command | Ready when it prints |
| --- | --- | --- |
| 0 | `cloudflared tunnel --url http://localhost:8000` | `https://<random>.trycloudflare.com` |
| 1 | `source ~/.tandemetry.env && uv run tandemetry migrate && uv run tandemetry serve` | `Uvicorn running on http://127.0.0.1:8000` |
| 2 | `source ~/.tandemetry.env && uv run tandemetry normalize` | `normalizing raw.github as tandemetry-normalizer` |
| 3 | `source ~/.tandemetry.env && uv run tandemetry consume` | `consuming events.normalized as tandemetry-clickhouse` |

1. Start the stack (`dc up -d --wait`, see [Start](#start)).
2. Start terminal 0 and copy the tunnel URL. The URL is new on every start: set the App's
   **Webhook URL** (App settings → **General**) to `https://<random>.trycloudflare.com/webhooks/github`
   and **Save changes**. Run one tunnel only.
3. Start terminals 1–3. `normalize` and `consume` then wait silently for messages.
4. App settings → **Advanced → Recent Deliveries** → `ping` → **Redeliver**: GitHub shows 204 and
   terminal 1 logs `POST /webhooks/github … 204`.
5. Work on an installed repository as usual (open a pull request, push, review, let CI run,
   merge); deliveries of subscribed events get 202 (`ping` and `installation.*` get 204). Check the result with the queries below.

Stop with Ctrl+C in each terminal, then `dc stop` or leave the stack running.

Without GitHub, send a signed delivery yourself (`serve` only needs the webhook secret):

```bash
body='{"action":"opened","repository":{"id":1296269,"full_name":"octocat/Hello-World"}}'
sig=$(printf '%s' "$body" | openssl dgst -sha256 -hmac "$TANDEMETRY_GITHUB__WEBHOOK_SECRET" | sed 's/^.* //')
curl -i localhost:8000/webhooks/github -H 'X-GitHub-Event: pull_request' \
  -H 'X-GitHub-Delivery: local-1' -H "X-Hub-Signature-256: sha256=$sig" --data-raw "$body"
                                     # HTTP/1.1 202 Accepted
curl -i localhost:8000/webhooks/github -H 'X-GitHub-Event: pull_request' \
  -H 'X-Hub-Signature-256: sha256=00' --data-raw "$body"   # HTTP/1.1 401 Unauthorized
dc exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server kafka:9092 \
  --topic raw.github --from-beginning --max-messages 1 --formatter-property print.key=true
```

This body is too short for the normalizer: it logs `skipped delivery local-1 … pull_request…`
and moves on. With the App installed, check what arrived from GitHub:

```bash
dc exec clickhouse sh -c 'clickhouse-client --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" -d "$CLICKHOUSE_DB" \
  -q "SELECT type, count() FROM events FINAL GROUP BY type ORDER BY type"'
dc exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group tandemetry-normalizer          # LAG 0 once everything is normalized
dc exec kafka /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server kafka:9092 \
  --describe --group tandemetry-clickhouse          # LAG 0 once everything is stored
```

Each completed CI job is one `check_run`, a submitted review one `review`, a merged pull request
one `pull_request` and one `merge`; the full mapping is in
[docs/github-app.md](../docs/github-app.md#5-check-deliveries).

Redeliver any delivery from the App's **Advanced** page: the counts stay the same. The table
briefly holds a second physical row with the same `event_id` (`SELECT count() FROM events`
grows), which `FINAL` and the next background merge remove.

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
- **Every webhook gets 401**: the secret differs from the App's, or something between GitHub and
  `serve` re-encoded the body. The signature covers the exact bytes GitHub sent.
- **`Authentication failed` for user `default`** from `migrate` or `consume`, or `normalize`
  asking for `TANDEMETRY_GITHUB__CLIENT_ID`: this terminal has not run `source ~/.tandemetry.env`.
- **The App's install page does not list a repository**: the repository belongs to an
  organization and the App to your personal account; transfer the App, see
  [docs/github-app.md](../docs/github-app.md#1-create-the-app).
- **Deliveries fail right after restarting `cloudflared`**: the tunnel URL changed; update the
  App's Webhook URL and **Redeliver**.
- **An extra `pull_request` with no matching delivery**: an earlier `publish-sample` message.
  It stays in `events.normalized` (the Kafka volume persists) and `consume` stores it like any
  other event.
- **`normalize` stops with `HTTP 401`**: wrong Client ID or private key, or the key was revoked.
- **`normalize` stops with "batch not normalized within 6000s"**: GitHub stayed rate limited or
  unavailable; start it again, the batch is retried.
- **Large deliveries get 503 on an older stack**: `raw.github` was created before
  `max.message.bytes` was set. Re-run `dc up -d --wait`; `kafka-init` applies the limit.
- **`up --wait` errors on `kafka-init`**: update Docker Compose to v2.17 or newer.
