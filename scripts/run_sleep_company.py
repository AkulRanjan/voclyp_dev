"""Run VoClyp for The Sleep Company: seed tenant + gateway + worker.

    py scripts/seed_sleep_company.py
    py scripts/run_sleep_company.py
"""
import atexit
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data" / "sleep-company"


def _lan_ip() -> str:
    """Best-effort LAN address so phones on the same Wi‑Fi can reach the API."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _ensure_mobile_env(lan: str) -> None:
    """Write voclyp-mobile/.env once if missing (Expo reads EXPO_PUBLIC_*)."""
    env_path = ROOT / "voclyp-mobile" / ".env"
    if env_path.exists():
        return
    env_path.write_text(
        f"# Auto-created for phone testing — update if your PC IP changes\n"
        f"EXPO_PUBLIC_API_URL=http://{lan}:8000\n",
        encoding="utf-8",
    )
    print(f"  Mobile .env created: EXPO_PUBLIC_API_URL=http://{lan}:8000")


def main():
    from scripts.seed_sleep_company import seed
    from voclyp.env import load_dotenv

    load_dotenv()  # SARVAM_API_KEY / AWS creds / overrides from .env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("VOCLYP_MASTER_KEY"):
        mk = DATA_DIR / "master_key.txt"
        if not mk.exists():
            mk.write_text(secrets.token_hex(32))
        os.environ["VOCLYP_MASTER_KEY"] = mk.read_text().strip()

    os.environ["VOCLYP_DATA_DIR"] = str(DATA_DIR)
    # Auto-select the real Sarvam pipeline (diarized batch STT + translate +
    # voiceprint speaker labeling) when a key is present; otherwise run the
    # dependency-free stub pipeline so the demo works without credits.
    if not os.environ.get("VOCLYP_PIPELINE_CONFIG"):
        has_sarvam = bool(os.environ.get("SARVAM_API_KEY"))
        config = "pipeline.sarvam.json" if has_sarvam else "pipeline.json"
        os.environ["VOCLYP_PIPELINE_CONFIG"] = str(ROOT / "configs" / config)
    print(f"  pipeline:  {Path(os.environ['VOCLYP_PIPELINE_CONFIG']).name}"
          f" (SARVAM_API_KEY {'set' if os.environ.get('SARVAM_API_KEY') else 'not set'})")

    seed(DATA_DIR)

    worker = subprocess.Popen(
        [sys.executable, "-m", "voclyp.worker", "--data-dir", str(DATA_DIR)],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    atexit.register(worker.terminate)

    import uvicorn
    from voclyp.gateway.app import create_app

    lan = _lan_ip()
    _ensure_mobile_env(lan)
    print("\n  The Sleep Company stack:")
    print(f"    PC only:     http://127.0.0.1:8000")
    print(f"    Phone (LAN): http://{lan}:8000")
    print("  Web console: cd web && npm run dev (proxies /v1 to :8000)")
    print("  Mobile: cd voclyp-mobile && npm start")
    print("          (uses EXPO_PUBLIC_API_URL from voclyp-mobile/.env)\n")

    # 0.0.0.0 so iOS/Android on the same Wi‑Fi can reach the API (not just localhost).
    uvicorn.run(create_app(data_dir=DATA_DIR), host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
