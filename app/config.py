import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

B2_KEY_ID = os.environ.get("B2_KEY_ID", "")
B2_APP_KEY = os.environ.get("B2_APP_KEY", "")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME", "character-vault")
B2_REGION = os.environ.get("B2_REGION", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GMI_API_KEY = os.environ.get("GMI_API_KEY", "")

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

DB_PATH = os.environ.get("DB_PATH", "character_vault.db")

GENERATE_API_KEY = os.environ.get("GENERATE_API_KEY", "")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Keyless generation: anyone can generate on the owner's provider keys, but
# rate-limited so a leaked URL can't drain the account. Sending the correct
# GENERATE_API_KEY bypasses all limits (owner / unlimited). Costs are counted
# in "units" — roughly one draft image = 1 unit, a video = VIDEO_UNITS.
# All configurable via the host's env without a redeploy.
RATE_IP_PER_HOUR = _int_env("RATE_IP_PER_HOUR", 25)        # units / IP / hour
RATE_GLOBAL_PER_DAY = _int_env("RATE_GLOBAL_PER_DAY", 400)  # units / day (all users)
RATE_VIDEO_PER_DAY = _int_env("RATE_VIDEO_PER_DAY", 12)     # videos / day (all users)
VIDEO_UNITS = _int_env("VIDEO_UNITS", 20)                   # cost weight of one video
MAX_KEYLESS_BATCH = _int_env("MAX_KEYLESS_BATCH", 10)       # frames per batch without the key

# Portfolio mode: the app is linked publicly, so a visitor should be able to
# try it end-to-end exactly once without being able to drain the account.
# Each workspace therefore carries its own *lifetime* unit budget, persisted
# in SQLite — the RateLimiter above lives in RAM and resets on restart, which
# on an auto-restarting VM would hand out fresh budget for free.
#
# The default budget of 40 units buys roughly one full pass through the
# product: a character with a reference portrait (1), a handful of images
# (1 each), a voice line (1) and one video (VIDEO_UNITS = 20).
WORKSPACE_UNIT_QUOTA = _int_env("WORKSPACE_UNIT_QUOTA", 40)

# Workspaces one IP may create. Deliberately not 1: several people behind a
# single corporate NAT share one public IP, and a hard 1:1 would silently
# lock out every colleague after the first visitor from that company.
MAX_WORKSPACES_PER_IP = _int_env("MAX_WORKSPACES_PER_IP", 3)

# Timeline: encoded pieces of a cut are cached on disk between renders, keyed by
# everything that determines their bytes. Without it, nudging one clip's length
# re-encodes the whole film — which is what decides whether someone iterates
# three times or fifteen. Lives outside the repo tree so a redeploy can't serve
# stale pieces, and is capped so it can't fill the VM's disk.
SEQUENCE_CACHE_DIR = os.environ.get(
    "SEQUENCE_CACHE_DIR", os.path.join(tempfile.gettempdir(), "loomina-pieces")
)
SEQUENCE_CACHE_MAX_MB = _int_env("SEQUENCE_CACHE_MAX_MB", 1536)
