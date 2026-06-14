"""Run the VoClyp demo app: gateway (with the bundled web UI) + worker.

One command boots everything a live demo needs:

    python scripts/demo_app.py                 # stub pipeline — free, no credits
    python scripts/demo_app.py --mode sarvam   # real Saarika ASR + translate
                                               # (needs SARVAM_API_KEY; spends credits)

On first run it creates a demo tenant + API key and prints the key (also kept
in <data-dir>/api_key.txt so restarts reuse it). Open http://localhost:8000 —
the Field Agent page records/submits conversations, the Manager Dashboard
shows insights, credit usage, and delivery health live.

Microphone capture requires a secure context: use localhost on this machine,
or the typed-transcript tab when demoing over plain http on a LAN.
"""
import argparse
import atexit
import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PIPELINES = {
    "stub": ROOT / "configs" / "pipeline.json",
    "sarvam": ROOT / "configs" / "pipeline.sarvam.json",
}


def bootstrap(data_dir: Path) -> str:
    """Create (or reuse) the demo tenant, API key, and demo webhook."""
    from voclyp.store import Store

    store = Store(data_dir / "voclyp.db")
    store.create_tenant("demo-fmcg", "VoClyp Demo (FMCG)", "fmcg")

    key_file = data_dir / "api_key.txt"
    if key_file.exists():
        api_key = key_file.read_text().strip()
        if store.authenticate(api_key):
            return api_key
    api_key = store.create_api_key("demo-fmcg", scopes=("ingest", "read", "admin"))
    key_file.write_text(api_key)

    if not store.list_endpoints("demo-fmcg"):
        # log:// sink stands in for the future CRM connector so the
        # dashboard's delivery-health panel has real data to show.
        store.add_webhook("demo-fmcg", "log://crm-connector",
                          event_types=("conversation.insights.ready",))
    return api_key


def main():
    parser = argparse.ArgumentParser(description="VoClyp demo app launcher")
    parser.add_argument("--mode", choices=sorted(PIPELINES), default="stub",
                        help="stub = free deterministic pipeline; "
                             "sarvam = live Saarika ASR + translate (uses credits)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "demo-app"))
    args = parser.parse_args()

    if args.mode == "sarvam" and not os.environ.get("SARVAM_API_KEY"):
        sys.exit("--mode sarvam requires the SARVAM_API_KEY environment variable")

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Demo-only key handling: persisted beside the data so gateway, worker,
    # and restarts agree. Production sources this from a KMS (docs/SECURITY.md).
    if not os.environ.get("VOCLYP_MASTER_KEY"):
        mk_file = data_dir / "master_key.txt"
        if not mk_file.exists():
            mk_file.write_text(secrets.token_hex(32))
        os.environ["VOCLYP_MASTER_KEY"] = mk_file.read_text().strip()

    os.environ["VOCLYP_DATA_DIR"] = str(data_dir)
    os.environ["VOCLYP_PIPELINE_CONFIG"] = str(PIPELINES[args.mode])
    # the dashboard + agent pages poll; give the demo key generous headroom
    os.environ.setdefault("VOCLYP_RATE_LIMIT", "240")

    api_key = bootstrap(data_dir)

    worker = subprocess.Popen(
        [sys.executable, "-m", "voclyp.worker", "--data-dir", str(data_dir)],
        cwd=ROOT, env=os.environ.copy(),
    )
    atexit.register(worker.terminate)

    print()
    print(f"  mode:      {args.mode}"
          + ("  (live Sarvam — each recording spends credits)" if args.mode == "sarvam" else "  (free stubs)"))
    print(f"  data dir:  {data_dir}")
    print(f"  API key:   {api_key}")
    print(f"  web app:   http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}/app/")
    print()
    print("  paste the API key on the home page, then use Field Agent / Dashboard")
    print()

    import uvicorn
    from voclyp.gateway.app import create_app
    uvicorn.run(create_app(data_dir=data_dir), host=args.host, port=args.port,
                log_level="warning")


if __name__ == "__main__":
    main()
