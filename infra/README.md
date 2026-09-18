# Running Loomina on your own server

Status: 2026-09-18. The hackathon deployment on Railway is gone — `/health`
answers "Application not found" — so Loomina now runs as a container on a small
Hetzner VM behind an existing Caddy. `DEPLOY.md` describes the same thing for an
Oracle Ampere VM, including the traps of that provider; this file is the shorter
path when a server with Docker and Caddy already exists.

## What runs where

| Piece | Where |
|---|---|
| App | container `loomina`, image `loomina/app:1`, built from the repo root |
| SQLite | named volume `loomina_vault-data` at `/data/character_vault.db` |
| TLS and routing | the machine's existing Caddy, see `caddy.txt` |

`docker-compose.hetzner.yml` deliberately leaves out the Caddy service from the
root compose file: one Caddy per machine, not one per app. The container is not
published on the host either — the proxy reaches it over the shared Docker
network, so the app is never on the public IP in the clear.

**The volume is the whole point.** Workspace tokens live in that SQLite file,
and a token is the only way back into a workspace. An image-layer database would
be wiped by the next build and every shared link with it.

**Timeouts.** A video takes one to four minutes while the browser polls, so the
Caddy block raises the proxy timeouts. The defaults cut long runs off mid-flight.

## Setup

1. Point an A record at the server (DNS only, no CDN proxy — Caddy needs to
   answer the ACME challenge itself).
2. Copy the repo to `/opt/loomina/app-src`, build `loomina/app:1`, put
   `docker-compose.hetzner.yml` at `/opt/loomina/docker-compose.yml`.
3. Write `/opt/loomina/.env` (root, mode 600):
   `LOOMINA_SERVER=user@host bash infra/geheimnisse-setzen.sh` asks for each key
   with a hidden prompt and never stores anything locally.
4. Append `caddy.txt` to the Caddyfile and reload.

Keys that matter: `B2_KEY_ID` / `B2_APP_KEY` (every asset is written to
Backblaze B2), `OPENAI_API_KEY` (portraits), `GMI_API_KEY` (identity images,
video, voices — without it `/capabilities` returns an empty `video_models`) and
`GENERATE_API_KEY` (owner key, lifts every limit).

## Backup

`backup.sh`, daily 05:15 UTC via `loomina-backup.timer`: the volume as a
tarball, 14 days locally and in object storage. Generated images and videos live
in B2; what this backup protects is the record of who owns them.

The backup directory must belong to the service user before the first run —
`/opt/loomina` belongs to root, so `mkdir` inside the script would fail:

```bash
sudo install -d -o <user> -g <user> -m 700 /opt/loomina/backups
```

## Carrying an existing SQLite over

Stop the container, replace the file inside the volume, start it again:

```bash
docker run --rm -v loomina_vault-data:/data -v "$PWD":/neu alpine:3.20 \
  sh -c 'cp /neu/character_vault.db /data/character_vault.db && chown 1000:1000 /data/character_vault.db'
```

Opening the app afterwards still asks for a workspace token: the workspaces came
along, the browser's memory did not.
