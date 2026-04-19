"""
Asset classification and market-hours utilities.

Provides helpers to:
- Classify symbols as crypto vs stock
- Validate that a strategy doesn't mix crypto and stock symbols
- Check whether the current time falls within US equity market hours
"""

from datetime import datetime, time, timedelta
from typing import List, Literal
from zoneinfo import ZoneInfo

from ..services.data_retrieval.data_providers import AVAILABLE_CRYPTO_ASSETS

_CRYPTO_SET = set(AVAILABLE_CRYPTO_ASSETS)
_ET = ZoneInfo("America/New_York")

# Regular trading hours (Mon-Fri)
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)

# Extended trading hours (Mon-Fri)
_EXTENDED_OPEN = time(4, 0)
_EXTENDED_CLOSE = time(20, 0)


def classify_asset_type(symbols: List[str]) -> Literal["crypto", "stock"]:
    """Return 'crypto' if ALL symbols are crypto, otherwise 'stock'.

    Raises ValueError if the list mixes crypto and stock symbols.
    """
    validate_no_mixed_assets(symbols)
    if all(s.upper() in _CRYPTO_SET for s in symbols):
        return "crypto"
    return "stock"


def validate_no_mixed_assets(symbols: List[str]) -> None:
    """Raise ValueError if *symbols* contains both crypto and stock assets."""
    if not symbols:
        return
    upper = [s.upper() for s in symbols]
    crypto = [s for s in upper if s in _CRYPTO_SET]
    stock = [s for s in upper if s not in _CRYPTO_SET]
    if crypto and stock:
        raise ValueError(
            f"Strategies cannot mix crypto and stock symbols. "
            f"Crypto: {crypto}, Stock: {stock}"
        )


def is_within_market_hours(extended: bool = False) -> bool:
    """Check whether the current time is within US equity market hours.

    Regular hours: Mon-Fri 09:30-16:00 ET
    Extended hours: Mon-Fri 04:00-20:00 ET
    """
    now_et = datetime.now(tz=_ET)
    # Monday=0 … Friday=4
    if now_et.weekday() > 4:
        return False
    current = now_et.time()
    if extended:
        return _EXTENDED_OPEN <= current < _EXTENDED_CLOSE
    return _REGULAR_OPEN <= current < _REGULAR_CLOSE


def seconds_until_market_open(extended: bool = False) -> float:
    """Return seconds until the next market-open moment.

    If the market is currently open, returns 0.
    """
    now_et = datetime.now(tz=_ET)
    open_time = _EXTENDED_OPEN if extended else _REGULAR_OPEN
    close_time = _EXTENDED_CLOSE if extended else _REGULAR_CLOSE

    # If currently within hours, 0
    if now_et.weekday() <= 4:
        current = now_et.time()
        if open_time <= current < close_time:
            return 0.0

    # Find next weekday at open_time
    target = now_et.replace(
        hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0
    )
    if target <= now_et:
        target += timedelta(days=1)
    # Skip weekends
    while target.weekday() > 4:
        target += timedelta(days=1)

    return (target - now_et).total_seconds()
