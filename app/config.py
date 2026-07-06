import os

from dotenv import load_dotenv

load_dotenv()

B2_KEY_ID = os.environ.get("B2_KEY_ID", "")
B2_APP_KEY = os.environ.get("B2_APP_KEY", "")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME", "character-vault")
B2_REGION = os.environ.get("B2_REGION", "")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

DB_PATH = os.environ.get("DB_PATH", "character_vault.db")

GENERATE_API_KEY = os.environ.get("GENERATE_API_KEY", "")
