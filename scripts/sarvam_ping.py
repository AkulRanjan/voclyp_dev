"""Cheap connectivity check for the Sarvam API key (one translate call).

    py scripts/sarvam_ping.py

Loads SARVAM_API_KEY from .env (or the environment) and makes a single,
low-cost translate call to confirm the key is live before you run the full
pipeline. Costs ~1 credit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.config import load_settings
from voclyp.env import load_dotenv
from voclyp.providers.sarvam import SarvamClient, SarvamError

load_dotenv()
settings = load_settings()
if not settings.sarvam_api_key:
    sys.exit("SARVAM_API_KEY not set. Add it to .env and SAVE the file, then retry.")

print("key prefix:", settings.sarvam_api_key[:6] + "…")
try:
    resp = SarvamClient(settings.sarvam_api_key).translate(
        "Mujhe orthopaedic mattress chahiye", source="auto", target="en-IN")
    print("translate ->", resp.get("translated_text"))
    print("detected source:", resp.get("source_language_code"))
    print("KEY IS LIVE")
except SarvamError as exc:
    sys.exit(f"Sarvam error (key may be invalid or out of credits): {exc}")
