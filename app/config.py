import os

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
# All configurable via Railway env without a redeploy.
RATE_IP_PER_HOUR = _int_env("RATE_IP_PER_HOUR", 25)        # units / IP / hour
RATE_GLOBAL_PER_DAY = _int_env("RATE_GLOBAL_PER_DAY", 400)  # units / day (all users)
RATE_VIDEO_PER_DAY = _int_env("RATE_VIDEO_PER_DAY", 12)     # videos / day (all users)
VIDEO_UNITS = _int_env("VIDEO_UNITS", 20)                   # cost weight of one video
MAX_KEYLESS_BATCH = _int_env("MAX_KEYLESS_BATCH", 10)       # frames per batch without the key
