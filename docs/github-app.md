# GitHub App setup

Tandemetry reads GitHub through a **private, read-only GitHub App** that you create in your own
account or organization. GitHub sends the App's webhooks to `tandemetry serve`, and
`tandemetry normalize` calls the GitHub REST API as the App's installation. The App never writes
to repositories.

`deploy/github-app/manifest.json` is the source of truth for the App's settings; a test keeps it
read-only and in sync with the events Tandemetry handles.

## 1. Create the App

Create the App under the account that owns the repositories: a private App installs only on the
account that owns it, so an App in your personal account cannot see an organization's
repositories.

- Personal repositories: GitHub → **Settings → Developer settings → GitHub Apps → New GitHub App**.
- Organization repositories: the organization's **Settings → Developer settings → GitHub Apps →
  New GitHub App**. An App already created in a personal account moves with App settings →
  **Advanced → Transfer ownership** (needs organization owner rights); its Client ID, private key
  and webhook secret stay the same.

Fill in the values from the manifest:

| Field | Value |
| --- | --- |
| GitHub App name | any unique name, e.g. `Tandemetry (acme)` |
| Homepage URL | `https://github.com/tandemetry/tandemetry` |
| Webhook → Active | on |
| Webhook URL | `https://<your-host>/webhooks/github` (locally: the tunnel URL, see below) |
| Webhook secret | output of `openssl rand -hex 32` |
| Repository permissions | **Read-only**: Checks, Contents, Metadata, Pull requests. Everything else: No access |
| Subscribe to events | Check run, Pull request, Pull request review |
| Where can this GitHub App be installed? | Only on this account |

After **Create GitHub App**:

1. Copy the **Client ID** from the App's **General** page.
2. Under **Private keys**, click **Generate a private key**; a `.pem` file downloads. Keep it
   outside the repository (gitleaks blocks committing it) with `chmod 600`.

## 2. Install the App

App settings → **Install App** → **Install** next to the owning account → **Only select
repositories** → pick the repositories to analyse → **Install**. The permissions screen must show
only **Read** access. Recent Deliveries then shows `installation.created`.

Installing later on more repositories needs no Tandemetry change: each webhook carries its
installation id. Webhooks cover activity from the moment of installation; earlier history comes
from the backfill (see the [roadmap](roadmap.md)).

## 3. Configure Tandemetry

Keep the variables in one file outside the repository, for example `~/.tandemetry.env`, and
`source` it in every terminal that runs Tandemetry:

```bash
cat > ~/.tandemetry.env <<'EOF'
set -a; source /path/to/tandemetry/deploy/.env; set +a
export TANDEMETRY_CLICKHOUSE__USERNAME="$CLICKHOUSE_USER"
export TANDEMETRY_CLICKHOUSE__PASSWORD="$CLICKHOUSE_PASSWORD"
export TANDEMETRY_CLICKHOUSE__DATABASE="$CLICKHOUSE_DB"
export TANDEMETRY_GITHUB__WEBHOOK_SECRET='<webhook secret>'
export TANDEMETRY_GITHUB__CLIENT_ID='<client id>'
export TANDEMETRY_GITHUB__PRIVATE_KEY="$(cat /secure/path/tandemetry.pem)"
EOF
chmod 600 ~/.tandemetry.env
```

The quoted `'EOF'` writes the lines as they are; `$CLICKHOUSE_*` and the key are read when the
file is sourced. Exports typed directly into one terminal do not reach the others.

| Variable | Default | Used by |
| --- | --- | --- |
| `TANDEMETRY_API__HOST` / `TANDEMETRY_API__PORT` | `127.0.0.1` / `8000` | `serve` |
| `TANDEMETRY_GITHUB__API_URL` | `https://api.github.com` (GHES: `https://<host>/api/v3`) | `normalize` |
| `TANDEMETRY_GITHUB__REQUEST_TIMEOUT_S` | `10` | `normalize` |
| `TANDEMETRY_GITHUB__RETRY_INITIAL_S` / `RETRY_MAX_S` | `1` / `60` | `normalize` |
| `TANDEMETRY_GITHUB__RATE_LIMIT_MAX_WAIT_S` | `3600` | `normalize` |
| `TANDEMETRY_GITHUB__BATCH_DEADLINE_S` | `6000` | `normalize` |
| `TANDEMETRY_API__MAX_BODY_BYTES` | `26214400` (25 MiB) | `serve` |

`serve` refuses to start without the webhook secret, `normalize` without the Client ID and key.

## 4. Receive webhooks locally

GitHub must reach your machine over HTTPS. Use a tunnel that forwards the request body
byte-for-byte, for example a Cloudflare quick tunnel:

```bash
brew install cloudflared
cloudflared tunnel --url http://localhost:8000    # prints https://<random>.trycloudflare.com
```

Set the App's **Webhook URL** to `https://<random>.trycloudflare.com/webhooks/github` (the URL
changes on every start). Then run `serve` and `normalize` as in
[deploy/README.md](../deploy/README.md#receive-github-webhooks).

`gh webhook forward` does not support GitHub App webhooks. Proxies that re-encode the JSON body
break the signature check (every delivery gets 401).

## 5. Check deliveries

App settings → **Advanced → Recent Deliveries** lists each delivery with the response code:

| Code | Meaning |
| --- | --- |
| 202 | accepted onto `raw.github` |
| 204 | event not used by Tandemetry (e.g. `ping`) |
| 400 | signature valid, body malformed |
| 413 | body larger than `TANDEMETRY_API__MAX_BODY_BYTES` |
| 401 | signature mismatch: check the webhook secret |
| 503 | Kafka unavailable: fix it, then **Redeliver** |

**Redeliver** sends the same delivery again; it produces the same `event_id`s, so nothing is
counted twice.

Which deliveries become events:

| Delivery | Event in ClickHouse |
| --- | --- |
| `pull_request.opened` | `pull_request`, plus one `commit` per pull request commit |
| `pull_request.synchronize` (a push) | one `commit` per pull request commit |
| `pull_request.closed` (merged) | `pull_request` and `merge` |
| `pull_request.edited` / `reopened` / `closed` (not merged) | `pull_request` |
| other `pull_request.*` (labeled, assigned, …) | none |
| `pull_request_review.submitted` | `review` |
| `check_run.completed` | `check_run` (`check_run.created` is skipped) |
| `ping`, `installation.*` | none |

Commits are read only when a pull request is opened or pushed to, so a pull request opened
before the App was installed has no `commit` events until the backfill runs.
