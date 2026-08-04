# Deploying Loomina on an Oracle Cloud Always Free VM

Loomina needs three things most free tiers no longer give you: a Docker image
(for `ffmpeg`), a process that stays awake while a 1–4 minute video renders in
a background thread, and a disk that survives restarts — the SQLite holds the
workspace tokens, so losing it breaks every link you already shared.

An Oracle *Always Free* Ampere VM covers all three and stays free indefinitely.

---

## 1. Create the VM

Oracle Cloud console → **Compute → Instances → Create instance**:

| Setting | Value |
|---|---|
| Shape | **Ampere A1 Flex** (ARM), 2 OCPU / 12 GB — inside the Always Free allowance |
| Image | Ubuntu 24.04 |
| Boot volume | 50 GB |
| SSH keys | upload your public key |

Note the **public IPv4 address** at the end.

> A credit card is required for identity verification. Stay on shapes marked
> *Always Free eligible* and the account is not charged.

## 2. Open ports 80 and 443

Two independent firewalls have to allow traffic — forgetting the second is the
usual reason a fresh Oracle VM looks dead from outside.

**a) Security list** (console): Networking → VCN → Subnet → Security List →
add ingress rules, source `0.0.0.0/0`, TCP ports `80` and `443`.

**b) The VM's own iptables**, over SSH:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT && sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT && sudo netfilter-persistent save
```

## 3. Point a domain at it

Caddy issues a Let's Encrypt certificate automatically, but only for a real
hostname. Free option: create a subdomain at [duckdns.org](https://www.duckdns.org)
and set it to the VM's public IP.

Verify before continuing — a wrong record makes the certificate request fail:

```bash
dig +short loomina.duckdns.org
```

## 4. Install Docker

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git && sudo usermod -aG docker $USER && newgrp docker
```

## 5. Deploy

```bash
git clone https://github.com/mschwabengruber88/character-vault.git && cd character-vault
```

Put your real hostname into the `Caddyfile` (replace `loomina.example.com`),
then create the `.env`:

```bash
cp .env.example .env && nano .env
```

Fill in the B2, OpenAI and GMI keys, set `CORS_ORIGINS` to your public URL,
and pick a long random `GENERATE_API_KEY` — that key is what lets *you*
generate without spending the visitor budget:

```bash
openssl rand -hex 24
```

Start it:

```bash
docker compose up -d --build
```

The first build takes a few minutes on ARM. Then check:

```bash
curl https://loomina.duckdns.org/health
```

`{"status": "ok"}` means you are live. If not, `docker compose logs -f caddy`
shows the certificate handshake.

## 6. Updating later

```bash
cd character-vault && git pull && docker compose up -d --build
```

The `vault-data` volume is untouched by a rebuild, so characters, assets and
workspace tokens survive.

---

## What visitors get

The app is deliberately usable **without** an API key, so someone you applied
to can try it immediately. What protects the account:

- **A lifetime budget per workspace** (`WORKSPACE_UNIT_QUOTA`, default 40
  units; one image = 1, one video = 20). Stored in SQLite, so a restart does
  not hand out fresh budget.
- **A cap on workspaces per IP** (`MAX_WORKSPACES_PER_IP`, default 3). Not 1
  on purpose: colleagues in one company share a public IP, and a hard 1 would
  lock out everyone after the first visitor.
- **Automatic refunds.** Units are drawn before generating, so a failed
  provider call, a rejected duplicate run or a cancelled batch hands them
  back — a GMI outage must not end someone's demo.
- **Daily global backstops** (`RATE_GLOBAL_PER_DAY`, `RATE_VIDEO_PER_DAY`)
  as a ceiling across all visitors combined.

Sending `X-API-Key: <GENERATE_API_KEY>` bypasses all of it.

### Tuning the spend

Rough worst case per day: `RATE_GLOBAL_PER_DAY` units, of which at most
`RATE_VIDEO_PER_DAY` are videos. Lower either one for a harder ceiling — both
take effect on `docker compose up -d`, no rebuild needed.

## Backing up

Everything generated lives in B2; only the metadata is local. Copy it off the
volume now and then:

```bash
docker compose cp app:/data/character_vault.db ./backup-$(date +%F).db
```
