"""Seed The Sleep Company demo tenant: stores, areas, users, API key.

Usage:
    python scripts/seed_sleep_company.py
    python scripts/seed_sleep_company.py --data-dir data/sleep-company
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TENANT = "the-sleep-company"
DEMO_PASSWORD = "SleepDemo123!"


def seed(data_dir: Path) -> None:
    from voclyp.store import Store

    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(data_dir / "voclyp.db")

    store.create_tenant(TENANT, "The Sleep Company", "sleep_company", region="in")

    users = {}
    for email, name, role in [
        ("area@voclyp.com", "Area Manager", "area_manager"),
        ("store@voclyp.com", "Store Manager", "store_manager"),
        ("sales@voclyp.com", "Sales Rep", "sales"),
        ("admin@voclyp.com", "Admin", "admin"),
    ]:
        try:
            uid = store.create_user(email, name, role, TENANT, DEMO_PASSWORD)
        except ValueError:
            user = store.verify_user_password(email, DEMO_PASSWORD)
            uid = user["user_id"] if user else None
        users[role] = uid

    store.create_area(TENANT, "mumbai-west", "Mumbai West", users["area_manager"], region="Maharashtra")
    store.set_user_role_scope(TENANT, users["area_manager"], "area_manager", area_id="mumbai-west")

    stores = [
        ("tsc-andheri", "The Sleep Company — Andheri", users["store_manager"]),
        ("tsc-bandra", "The Sleep Company — Bandra", users["store_manager"]),
        ("tsc-thane", "The Sleep Company — Thane", users["store_manager"]),
    ]
    for sid, name, mgr in stores:
        store.create_store(
            TENANT, sid, name, "mumbai-west", mgr,
            region="Maharashtra", address_full=name,
        )

    store.set_user_role_scope(
        TENANT, users["store_manager"], "store_manager",
        area_id="mumbai-west", store_ids=["tsc-andheri", "tsc-bandra"],
    )
    store.set_user_role_scope(
        TENANT, users["sales"], "sales",
        area_id="mumbai-west", store_ids=["tsc-andheri"],
    )

    key_file = data_dir / "api_key.txt"
    if key_file.exists() and store.authenticate(key_file.read_text().strip()):
        api_key = key_file.read_text().strip()
    else:
        api_key = store.create_api_key(TENANT, scopes=("ingest", "read", "admin"))
        key_file.write_text(api_key)

    if not store.list_endpoints(TENANT):
        store.add_webhook(TENANT, "log://crm-connector", event_types=("conversation.insights.ready",))

    print()
    print("  The Sleep Company tenant seeded")
    print(f"  data dir:  {data_dir}")
    print(f"  tenant:    {TENANT}")
    print(f"  API key:   {api_key}")
    print()
    print("  Demo logins (password for all):", DEMO_PASSWORD)
    print("    area@voclyp.com   — area_manager")
    print("    store@voclyp.com  — store_manager")
    print("    sales@voclyp.com  — sales rep")
    print("    admin@voclyp.com  — admin")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "sleep-company"))
    args = parser.parse_args()
    seed(Path(args.data_dir))


if __name__ == "__main__":
    main()
