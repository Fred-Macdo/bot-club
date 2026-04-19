"""
Quick test: verify close_position works for DOGE with the symbol fix.
Run from within the backend container or locally with env vars set.

Usage:
  DRY_RUN=1 python test_close_doge.py        # just check position, don't sell
  python test_close_doge.py                    # actually close the DOGE position
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.services.trading.alpaca_client import AlpacaTradingClient
from src.models.user_config import ConfigEncryption

# ---------- load keys ----------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "bot_club_db")

# Try to get keys from env first, then from DB
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

if not api_key or not secret_key:
    from pymongo import MongoClient

    db = MongoClient(MONGO_URL)[MONGO_DB_NAME]
    # Find the first user with Alpaca config
    user = db.users.find_one({"alpaca_config": {"$exists": True}})
    if user and user.get("alpaca_config"):
        cfg = ConfigEncryption.decrypt_config(user["alpaca_config"])
        api_key = cfg.get("api_key")
        secret_key = cfg.get("secret_key")
        print(f"Loaded keys for user: {user.get('email', user['_id'])}")
    else:
        print(
            "ERROR: No Alpaca keys found. Set ALPACA_API_KEY / ALPACA_SECRET_KEY env vars."
        )
        sys.exit(1)

# ---------- init client ----------
client = AlpacaTradingClient(api_key, secret_key, paper=True)

# 1. Show all positions
print("\n=== Current Positions ===")
positions = client.get_positions()
for p in positions:
    print(f"  {p['symbol']}  qty={p['qty']}  market_value={p.get('market_value')}")

if not positions:
    print("  (no positions)")
    sys.exit(0)

# 2. Check DOGE specifically
print("\n=== Checking DOGE position ===")
doge_pos = client.get_position("DOGE/USD")  # should use _position_symbol -> DOGEUSD
if doge_pos:
    print(f"  Found: {doge_pos['symbol']}  qty={doge_pos['qty']}")
else:
    print("  No DOGE position found via get_position('DOGE/USD')")
    # Try bare symbol too
    doge_pos = client.get_position("DOGE")
    if doge_pos:
        print(f"  Found via bare 'DOGE': {doge_pos['symbol']}  qty={doge_pos['qty']}")

# 3. Close if not dry run
dry_run = os.getenv("DRY_RUN", "0") == "1"
if dry_run:
    print("\n[DRY RUN] Skipping actual close. Unset DRY_RUN to sell.")
else:
    if doge_pos:
        print("\n=== Closing DOGE position ===")
        try:
            result = client.close_position("DOGE/USD")
            print(
                f"  Order submitted: id={result.get('id')} status={result.get('status')}"
            )
            # Wait for fill
            filled = client.wait_for_order_fill(result["id"], timeout=15)
            print(
                f"  Fill status: {filled.get('status')}  avg_price={filled.get('filled_avg_price')}"
            )
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("\nNo DOGE position to close.")
