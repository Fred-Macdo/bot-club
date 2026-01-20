import redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

def unlock():
    try:
        r = redis.from_url(REDIS_URL)
        key = "lock:alpaca_strategy"
        if r.exists(key):
            val = r.get(key)
            print(f"Lock found: {val}. Deleting...")
            r.delete(key)
            print("Lock deleted.")
        else:
            print("No lock found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    unlock()
