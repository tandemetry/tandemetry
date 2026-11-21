# GitHub App setup

Tandemetry reads GitHub through a **private, read-only GitHub App** that you create in your own
account or organization. GitHub sends the App's webhooks to `tandemetry serve`, and
`tandemetry normalize` calls the GitHub REST API as the App's installation. The App never writes
to repositories.

`deploy/github-app/manifest.json` is the source of truth for the App's settings; a test keeps it
read-only and in sync with the events Tandemetry handles.

## 1. Create the App

GitHub → **Settings → Developer settings → GitHub Apps → New GitHub App** (for an organization:
the organization's **Settings → Developer settings**). Fill in the values from the manifest:

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

App page → **Install App** → choose the account → **Only select repositories** → pick the
repositories to analyse. Installing later on more repositories needs no Tandemetry change: each
webhook carries its installation id.

## 3. Configure Tandemetry

```bash
export TANDEMETRY_GITHUB__WEBHOOK_SECRET=<webhook secret>      # serve
export TANDEMETRY_GITHUB__CLIENT_ID=<client id>                # normalize
export TANDEMETRY_GITHUB__PRIVATE_KEY="$(cat /secure/path/tandemetry.pem)"   # normalize
```

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
