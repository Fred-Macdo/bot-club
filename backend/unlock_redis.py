import redis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def unlock():
    try:
        r = redis.from_url(REDIS_URL)
        keys = r.keys("lock:alpaca_strategy:*")
        if keys:
            for key in keys:
                val = r.get(key)
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                print(f"Lock found: {key_str} = {val}. Deleting...")
                r.delete(key)
            print(f"Deleted {len(keys)} lock(s).")
        else:
            print("No locks found.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    unlock()
