# Character Vault

A generative-media backend for AI character assets — built for the
[Backblaze Generative AI Media Hackathon](https://backblaze-generative-media.devpost.com/).

Character Vault lets you create a character profile, then generate a portrait
(OpenAI DALL-E) and voice lines (ElevenLabs TTS) for it. Every generated asset
is pushed straight to Backblaze B2 through [Genblaze](https://github.com/backblaze-labs/genblaze),
which produces a SHA-256 provenance manifest for each run — so every asset in
the vault is traceable back to the exact provider, model, and prompt that made it.

## Providers & models used

| Purpose          | Provider   | Model         |
|-------------------|-----------|---------------|
| Storage           | Backblaze B2 (via `genblaze-s3`) | S3-compatible object storage |
| Character portrait | OpenAI (`genblaze-openai`) | `gpt-image-1` |
| Character voice line | ElevenLabs (`genblaze-elevenlabs`), falls back to OpenAI TTS (`genblaze-openai`) on failure | `eleven_v3` / `gpt-4o-mini-tts` |

## B2 + Genblaze usage

Every `/generate/*` endpoint builds a `genblaze_core.Pipeline`, runs a single
`Step` against the relevant provider, and writes the result through an
`ObjectStorageSink` backed by `S3StorageBackend.for_backblaze(bucket)`. The
pipeline run returns a verified provenance `Manifest` alongside the asset URL;
both the URL and the manifest's `sha256`/verification result are persisted in
the local metadata store (SQLite) next to the character record.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in B2 / OpenAI / ElevenLabs credentials
uvicorn app.main:app --reload
```

Check it's alive:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## API

- `POST /characters` `{name, description}` — create a character
- `GET /characters` — list characters
- `GET /characters/{id}` — character detail incl. generated assets
- `POST /characters/{id}/generate/image` `{prompt}` — generate + store a portrait
- `POST /characters/{id}/generate/voice` `{text}` — generate + store a voice line

## Deploy (Railway)

1. Push this repo to GitHub.
2. Railway → New Project → Deploy from GitHub Repo.
3. Set the variables from `.env.example` in Railway's Variables tab.
4. Railway builds from the included `Dockerfile` and injects `$PORT` automatically.
5. Verify `https://<your-railway-url>/health` returns `{"status": "ok"}`.
