# Deploying Loomina on an Oracle Cloud VM

Loomina needs three things most free tiers no longer give you: a Docker image
(for `ffmpeg`), a process that stays awake while a 1–4 minute video renders in
a background thread, and a disk that survives restarts — the SQLite holds the
workspace tokens, so losing it breaks every link you already shared.

An Oracle Ampere VM covers all three. This guide is written from an actual
run-through and includes the traps that cost hours the first time.

---

## Read this first: Ampere capacity

`VM.Standard.A1.Flex` is the shape you want, and in busy regions it is often
simply unavailable. In Frankfurt (2026-08) **all three availability domains
returned "Out of capacity"** on real creation attempts — that is not a
configuration error, and retrying the form in the same minute does not fix it.

What actually helps:

- **Upgrade the account to Pay As You Go.** Oracle gives upgraded accounts
  priority access to hardware. Always Free resources stay free; you are only
  charged above the limits (currently 2 OCPU / 12 GB Ampere, halved from
  4 / 24 on 2026-06-15). Card verification places a *hold* of roughly
  €93 / $100 that is released rather than debited — set a budget alarm anyway.
- **Save the instance config as a stack** (button on the review page) so each
  retry is one click instead of the whole wizard.
- **Retry over hours or days.** Capacity frees up in waves.

The AMD Always Free shape `VM.Standard.E2.1.Micro` is a fallback, with two
catches: it exists **only in AD-3**, and it has **1 GB RAM**, which is tight
for ffmpeg encoding. Selecting any other AD silently switches the shape back
to A1.Flex.

## Step 0 — create the VCN *first*, via the wizard

Do not let the instance form create the network inline. That path is
deliberately limited: the **"Automatically assign public IPv4 address" toggle
stays disabled**, with the message *"You must select a public subnet"*, and
the instance ends up unreachable from the internet. The form admits it in
small print — *"There are additional options available when you use the
Networking pages"*.

Instead: **Networking → Virtual cloud networks → Actions → Start VCN Wizard →
"Create VCN with Internet Connectivity"**. Name it, accept the defaults. That
creates the VCN, a public and a private subnet, an internet gateway, a NAT
gateway, a service gateway and the route tables in one pass.

Back in the instance form, pick that VCN and its public subnet — the public IP
toggle then switches itself on.

## Step 0b — the SSH key goes into cloud-init

The current create-instance wizard has **no SSH key field at all**. Put the
key in the initialization script instead:

**Basic information → Advanced options → Initialization script → Paste
cloud-init script**

```yaml
#cloud-config
ssh_authorized_keys:
  - ssh-ed25519 AAAA...your-public-key... you@example.com
package_update: true
packages:
  - docker.io
  - docker-compose-v2
  - git
  - iptables-persistent
runcmd:
  - [ iptables, -I, INPUT, "6", -m, state, --state, NEW, -p, tcp, --dport, "80", -j, ACCEPT ]
  - [ iptables, -I, INPUT, "6", -m, state, --state, NEW, -p, tcp, --dport, "443", -j, ACCEPT ]
  - [ netfilter-persistent, save ]
  - [ usermod, -aG, docker, ubuntu ]
  - [ systemctl, enable, --now, docker ]
```

This also installs Docker and opens the VM-side firewall, so those steps are
already done when the machine boots.

Get your key with `cat ~/.ssh/id_ed25519.pub`. Only the **public** key goes
here — never the private one.

On clicking Create, Oracle warns **"No SSH access"** because *its own* key
field is empty. That warning is expected; the key arrives via cloud-init.

## 1. Create the VM

**Compute → Instances → Create instance**:

| Setting | Value |
|---|---|
| Availability domain | any — try all three if capacity fails |
| Image | **Canonical Ubuntu 24.04** (via "Change image") |
| Shape | **VM.Standard.A1.Flex**, 1 OCPU / 6 GB is plenty |
| Networking | **Select existing** → the VCN from step 0 → its **public** subnet |
| Public IPv4 | must be **on** |
| Boot volume | default (~47 GB) is fine |

## 2. Open ports 80 and 443 in the security list

cloud-init handles the VM's own iptables. The second firewall lives in the
console and still needs doing — forgetting it is the usual reason a fresh VM
looks dead from outside:

**Networking → VCN → your VCN → Security Lists → Default Security List →
Add Ingress Rules**, source `0.0.0.0/0`, TCP destination ports `80` and `443`.

## 3. Point a domain at it

Caddy issues a Let's Encrypt certificate automatically, but only for a real
hostname whose A record already points at the VM's public IP. Free option: a
subdomain at [duckdns.org](https://www.duckdns.org).

Verify before continuing — a wrong record makes the certificate request fail:

```bash
dig +short loomina.duckdns.org
```

## 4. Deploy

```bash
ssh ubuntu@<your-vm-ip>
```

```bash
git clone https://github.com/mschwabengruber88/character-vault.git && cd character-vault
```

Put your hostname into the `Caddyfile` (replace `loomina.example.com`), then:

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

`{"status": "ok"}` means you are live. If not: `docker compose logs -f caddy`
shows the certificate handshake, and `cloud-init status --long` tells you
whether the init script finished.

## 5. Updating later

```bash
cd character-vault && git pull && docker compose up -d --build
```

The `vault-data` volume is untouched by a rebuild, so characters, assets and
workspace tokens survive.

## Set a budget alarm

If you upgraded to Pay As You Go, do this immediately:

**Billing & Cost Management → Budgets → Create Budget**, amount **1 €**,
alert threshold 100 %, your email. Always Free resources cost nothing, but a
real payment method is now on file — you want to hear about the first cent.

---

## What visitors get

The app is deliberately usable **without** an API key, so someone you applied
to can try it immediately. What protects the account:

- **A lifetime budget per workspace** (`WORKSPACE_UNIT_QUOTA`, default 40
  units; one image = 1, one video = 20). Stored in SQLite, so a restart does
  not hand out fresh budget. The topbar shows the remaining count.
- **A cap on workspaces per IP** (`MAX_WORKSPACES_PER_IP`, default 3). Not 1
  on purpose: colleagues in one company share a public IP, and a hard 1 would
  lock out everyone after the first visitor.
- **Automatic refunds.** Units are drawn before generating, so a failed
  provider call, a rejected duplicate run or a cancelled batch hands them
  back — a GMI outage must not end someone's demo.
- **Daily global backstops** (`RATE_GLOBAL_PER_DAY`, `RATE_VIDEO_PER_DAY`).

Sending `X-API-Key: <GENERATE_API_KEY>` bypasses all of it.

## Backing up

Everything generated lives in B2; only the metadata is local. Copy it off the
volume now and then:

```bash
docker compose cp app:/data/character_vault.db ./backup-$(date +%F).db
```
