# Loomina

**One character. Every medium. Always consistent.**

Loomina turns a single character profile into a full library of images, scenes,
voiceover and video — keeping the same face, style and identity across all of
them. No model training, no LoRA.

Built for the [Backblaze Generative AI Media Hackathon](https://backblaze-generative-media.devpost.com/).
Every generated asset is written to Backblaze B2 through
[Genblaze](https://github.com/backblaze-labs/genblaze), which produces a
SHA-256 provenance manifest per run — so each asset traces back to the exact
provider, model and prompt that made it.

---

## How identity is held

A character is a record: name, appearance, **personality**, purpose, a fixed
**seed** and a fixed **voice**. Its own stored portraits then become the
reference images for everything generated afterwards, so identity is carried by
image conditioning rather than by fine-tuning. A character stays recognisable
across a photoshoot, a multi-character scene and a video — in seconds, with no
training step.

## What it does

| Area | Modes |
|---|---|
| **Images** | Single image, variation set, photoshoot, story series, multi-character scene, photo art, background plates |
| **Video** | Animate a character (image→video), scene, **motion comic** (panels timed to their own dialogue) |
| **Audio** | Single voice line, multi-speaker dialogue |
| **Script** | Idea → shootable script; a story script drops straight into the story image mode, one line per panel |
| **Canvas** | Manga panels, speech bubbles, soundwords, stickers, text and shapes; save layouts as templates; burn a composition over a video |

Other things worth knowing:

- **AI disclosure per generation** — either a visible "AI" badge burned into
  the corner (survives screenshots) or the provenance manifest embedded
  invisibly in the PNG. The untouched original stays in B2 either way, so the
  manifest's hash chain over it remains intact.
- **Waste-aware** — draft and final quality tiers, a live cost estimate before
  each run, batch generation with a stop button, and a duplicate-request guard.
- **Multi-tenant** — every character, asset and video lives in a workspace.
  The workspace id is the token the client sends as `X-Workspace-Id`; data from
  other workspaces is unreachable, even by guessing row ids.
- **Bilingual UI** (German / English) and a private B2 bucket fronted by
  short-lived presigned URLs.

## Providers & models

| Purpose | Provider | Model |
|---|---|---|
| Storage | Backblaze B2 (`genblaze-s3`) | S3-compatible object storage |
| Portrait / images | OpenAI (`genblaze-openai`) | `gpt-image-1` |
| Identity images & scenes | GMI Cloud | `gemini-2.5-flash-image` (Nano Banana) |
| Video | GMI Cloud | Kling 2.1 (i2v / t2v), Pixverse 5.6 (i2v / t2v), Veo 3 Fast |
| Lip-sync | GMI Cloud | `kling-lip-sync` |
| Voice | GMI Cloud Inworld TTS, falling back to OpenAI | `inworld-tts-2` / `gpt-4o-mini-tts` |
| Script | OpenAI | `gpt-4o-mini` |

Models whose key is missing are hidden from the UI rather than failing at
generation time.

## Requirements

- Python 3.12+
- **ffmpeg** on `PATH` (audio mux, poster frames, video overlay, motion comics)
- Accounts: Backblaze B2, OpenAI, GMI Cloud

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Fill in the B2, OpenAI and GMI credentials, then:

```bash
uvicorn app.main:app --reload
```

The web UI is served at `/`. Check it's alive:

```bash
curl http://localhost:8000/health
```

Run the tests:

```bash
python -m pytest tests/ -q
```

## API

Interactive docs at `/docs`. The main groups:

| Group | Endpoints |
|---|---|
| Workspaces | `POST /workspaces`, `GET /workspaces/current` |
| Characters | `GET/POST /characters`, `GET/PATCH/DELETE /characters/{id}`, `POST /characters/{id}/reference`, `PUT /characters/{id}/voice` |
| Images | `POST /characters/{id}/generate/image`, `POST /characters/{id}/generate/batch`, `GET /batches/{id}`, `POST /batches/{id}/cancel` |
| Scenes & studio | `GET/POST/DELETE /scenes`, `GET/POST/DELETE /studio` |
| Audio | `POST /characters/{id}/generate/voice`, `GET/POST/DELETE /audio`, `GET/POST/DELETE /audio/dialogue` |
| Video | `GET/POST/DELETE /videos`, `GET /videos/{id}/poster`, `POST /videos/{id}/overlay`, `POST /videos/motion-comic` |
| Canvas | `POST /canvas/export`, `GET/POST/PUT/DELETE /canvas/templates` |
| Scripts | `GET/POST/DELETE /scripts` |
| Meta | `GET /health`, `GET /capabilities`, `GET /voices` |

Every data endpoint requires an `X-Workspace-Id` header.

## Limits on a public link

Generation is deliberately usable **without** an API key, so a visitor can try
the app immediately. Four things keep that from draining the account:

- **A lifetime budget per workspace** (`WORKSPACE_UNIT_QUOTA`, default 40
  units; an image costs 1, a video 20). It lives in SQLite, so a restart does
  not hand out fresh budget. The UI shows the remaining count in the topbar.
- **A cap on workspaces per IP** (`MAX_WORKSPACES_PER_IP`, default 3). Not 1
  on purpose: colleagues in one company share a public IP, and a hard 1 would
  lock out everyone after the first visitor.
- **Automatic refunds** — units are drawn before generating, so a failed
  provider call, a rejected duplicate run or a cancelled batch hands them back.
- **Daily global backstops** (`RATE_GLOBAL_PER_DAY`, `RATE_VIDEO_PER_DAY`).

Sending `X-API-Key: <GENERATE_API_KEY>` bypasses all of it. See
[.env.example](.env.example) for every knob.

## Deploying

See **[DEPLOY.md](DEPLOY.md)** for a full walkthrough on an Oracle Cloud
Always Free VM (Docker + Caddy with automatic TLS).

Loomina needs a host that can run a Docker image (for `ffmpeg`), stay awake
while a 1–4 minute video renders in a background thread, and keep a persistent
disk — the SQLite holds the workspace tokens, so losing it breaks links that
were already shared. That rules out static and serverless hosts.

```bash
docker compose up -d --build
```

## Layout

```
app/
  main.py        FastAPI routes, rate limits, workspace budgets
  pipelines.py   Provider calls — image, video, voice, script, lip-sync
  db.py          SQLite schema, migrations, per-workspace queries
  storage.py     Presigned B2 URLs
  disclosure.py  Visible badge / embedded manifest
  static/        UI — no build step (index.html, app.js, canvas.js, styles.css)
tests/           pytest suite
```
