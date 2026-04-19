# backend/src/services/data_providers.py
from abc import ABC, abstractmethod
import polars as pl
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, Any, Tuple, Union, List
import yfinance as yf
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

TIMEFRAME_MAPPINGS = {
    "1MIN": {"yahoo": "1m", "alpaca": "1Min", "polygon": ("minute", 1)},
    "2MIN": {"yahoo": "2m", "alpaca": "2Min", "polygon": ("minute", 2)},
    "5MIN": {"yahoo": "5m", "alpaca": "5Min", "polygon": ("minute", 5)},
    "15MIN": {"yahoo": "15m", "alpaca": "15Min", "polygon": ("minute", 15)},
    "30MIN": {"yahoo": "30m", "alpaca": "30Min", "polygon": ("minute", 30)},
    "60MIN": {"yahoo": "60m", "alpaca": "1Hour", "polygon": ("hour", 1)},
    "1HOUR": {"yahoo": "60m", "alpaca": "1Hour", "polygon": ("hour", 1)},
    "1H": {"yahoo": "60m", "alpaca": "1Hour", "polygon": ("hour", 1)},
    "1d": {"yahoo": "1d", "alpaca": "1Day", "polygon": ("day", 1)},
    "1D": {"yahoo": "1d", "alpaca": "1Day", "polygon": ("day", 1)},
    "2D": {"yahoo": "2d", "alpaca": "2Day", "polygon": ("day", 2)},
    "5D": {"yahoo": "5d", "alpaca": "5Day", "polygon": ("day", 5)},
    "1wk": {"yahoo": "1wk", "alpaca": "1Week", "polygon": ("week", 1)},
    "1w": {"yahoo": "1wk", "alpaca": "1Week", "polygon": ("week", 1)},
    "1W": {"yahoo": "1wk", "alpaca": "1Week", "polygon": ("week", 1)},
    "1mo": {"yahoo": "1mo", "alpaca": "1Month", "polygon": ("month", 1)},
    "3mo": {"yahoo": "3mo", "alpaca": "3Month", "polygon": ("month", 3)},
}

AVAILABLE_CRYPTO_ASSETS = [
    "AAVE",
    "AVAX",
    "BAT",
    "BCH",
    "BTC",
    "CRV",
    "DOGE",
    "DOT",
    "ETH",
    "GRT",
    "LINK",
    "LTC",
    "MKR",
    "PEPE",
    "SHIB",
    "SOL",
    "SUSHI",
    "TRUMP",
    "UNI",
    "USDC",
    "USDG",
    "USDT",
    "XRP",
    "XTZ",
    "YFI",
]

ALPACA_RESPONSE_CODES = {
    200: "Success",
    400: """One of the request parameters is invalid. See the returned message for details.""",
    403: """Authentication headers are missing or invalid. 
    Make sure you authenticate your request with a valid API key.""",
    429: """Too many requests. You hit the rate limit. 
    Use the X-RateLimit-... response headers to make sure you're under the rate limit.""",
    500: """Internal server error. We recommend retrying these later. 
    If the issue persists, please contact us on Slack or on the Community Forum.""",
}


class BaseDataProvider(ABC):
    """Abstract base class for data providers"""

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> pl.DataFrame:
        """Get historical OHLCV data"""
        pass

    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol"""
        pass

    @abstractmethod
    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        """Get crypto quote from Provider"""
        pass

    def get_provider_timeframe(
        self, timeframe: str
    ) -> Union[str, Tuple[str, int], None]:
        """Get the provider-specific timeframe mapping"""
        provider_name = self.get_provider_name()
        if timeframe in TIMEFRAME_MAPPINGS:
            return TIMEFRAME_MAPPINGS[timeframe].get(provider_name)
        return None

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name for timeframe mapping"""
        pass


class YahooFinanceProvider(BaseDataProvider):
    """Yahoo Finance data provider"""

    def get_provider_name(self) -> str:
        return "yahoo"

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> pl.DataFrame:
        """Get historical data from Yahoo Finance"""
        loop = asyncio.get_event_loop()

        def fetch_data():
            ticker = yf.Ticker(symbol)
            interval = self.get_provider_timeframe(timeframe) or "1d"
            df = ticker.history(
                start=start_date, end=end_date, interval=interval, auto_adjust=True
            )

            # Normalize columns
            df.columns = df.columns.str.lower()
            df = df.reset_index()

            # Rename 'Date' or 'Datetime' to 'timestamp'
            if "Date" in df.columns:
                df = df.rename(columns={"Date": "timestamp"})
            elif "Datetime" in df.columns:
                df = df.rename(columns={"Datetime": "timestamp"})

            required_columns = ["open", "high", "low", "close", "volume"]
            for col in required_columns:
                if col not in df.columns:
                    df[col] = 0.0

            if not df.empty:
                return pl.from_pandas(df)
            return pl.DataFrame()

        return await loop.run_in_executor(None, fetch_data)

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Yahoo Finance"""
        loop = asyncio.get_event_loop()

        def fetch_quote():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "symbol": symbol,
                "price": info.get("regularMarketPrice", 0),
                "bid": info.get("bid", 0),
                "ask": info.get("ask", 0),
                "volume": info.get("regularMarketVolume", 0),
                "timestamp": datetime.now(timezone.utc),
            }

        return await loop.run_in_executor(None, fetch_quote)

    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        logger.warning(
            "Yahoo Finance provider does not support bulk crypto quotes efficiently."
        )
        return pl.DataFrame()  # Must return empty DataFrame, not None


class AlpacaProvider(BaseDataProvider):
    """Alpaca Markets data provider"""

    STOCKS_BASE_URL = "https://data.alpaca.markets/v2/stocks"
    CRYPTO_BASE_URL = "https://data.alpaca.markets/v1beta3/crypto/us"

    # Common crypto symbols (without /USD suffix)
    CRYPTO_SYMBOLS = {
        "BTC",
        "ETH",
        "DOGE",
        "LTC",
        "BCH",
        "LINK",
        "UNI",
        "AAVE",
        "AVAX",
        "BAT",
        "CRV",
        "DOT",
        "GRT",
        "MKR",
        "SHIB",
        "SOL",
        "SUSHI",
        "XTZ",
        "YFI",
        "ALGO",
        "ATOM",
        "FIL",
        "MATIC",
        "XLM",
        "TRUMP",
        "PEPE",
        "USDG",
    }

    def __init__(self, api_key: str, secret_key: str, base_url: str = None):
        self.api_key = api_key
        self.secret_key = secret_key
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}

    def get_provider_name(self) -> str:
        return "alpaca"

    def _is_crypto_symbol(self, symbol: str) -> bool:
        # Check standard list or if it ends with USD
        base_symbol = symbol.replace("/USD", "").replace("-USD", "").upper()
        return base_symbol in self.CRYPTO_SYMBOLS or symbol.endswith("/USD")

    def _normalize_crypto_symbols(self, symbols: List[str]) -> List[str]:
        normalized = []
        for symbol in symbols:
            base = symbol.replace("/USD", "").replace("-USD", "").upper()
            normalized.append(f"{base}/USD")
        return normalized

    def _separate_symbols(self, symbols: List[str]) -> tuple[List[str], List[str]]:
        stocks = []
        crypto = []
        for symbol in symbols:
            if self._is_crypto_symbol(symbol):
                crypto.append(symbol)
            else:
                stocks.append(symbol)
        return stocks, crypto

    async def get_historical_data(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Day",
    ) -> pl.DataFrame:
        if isinstance(symbols, str):
            symbols = [symbols]

        stock_symbols, crypto_symbols = self._separate_symbols(symbols)
        all_data = []

        async with aiohttp.ClientSession() as session:
            if stock_symbols:
                stock_data = await self._fetch_stock_bars(
                    session, stock_symbols, start_date, end_date, timeframe
                )
                all_data.extend(stock_data)

            if crypto_symbols:
                crypto_data = await self._fetch_crypto_bars(
                    session, crypto_symbols, start_date, end_date, timeframe
                )
                all_data.extend(crypto_data)

        if not all_data:
            return pl.DataFrame()

        # Concat and Sort
        df = pl.concat(all_data)
        if "timestamp" in df.columns:
            df = df.sort("timestamp")
        return df

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        url = f"{self.STOCKS_BASE_URL}/snapshots"
        params = {"symbols": symbol}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self.headers, params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if symbol in data:
                        snap = data[symbol]
                        trade = snap.get("latestTrade", {})
                        quote = snap.get("latestQuote", {})
                        return {
                            "symbol": symbol,
                            "price": trade.get("p", 0),
                            "bid": quote.get("bp", 0),
                            "ask": quote.get("ap", 0),
                            "volume": snap.get("dailyBar", {}).get("v", 0),
                            "timestamp": datetime.now(timezone.utc),
                        }
        return {
            "symbol": symbol,
            "price": 0,
            "volume": 0,
            "timestamp": datetime.now(timezone.utc),
        }

    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        """Get current crypto quotes normalized to match Polygon schema"""
        if not symbols:
            return pl.DataFrame()

        _, crypto_symbols = self._separate_symbols(symbols)
        if not crypto_symbols:
            return pl.DataFrame()

        normalized = self._normalize_crypto_symbols(crypto_symbols)
        # Use v1beta3/crypto/us/snapshots
        url = f"{self.CRYPTO_BASE_URL}/snapshots"
        params = {"symbols": ",".join(normalized)}

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=self.headers, params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    snapshots = data.get("snapshots", {})

                    rows = []
                    for sym, snap in snapshots.items():
                        trade = snap.get("latestTrade", {})
                        quote = snap.get("latestQuote", {})
                        daily = snap.get("dailyBar", {})

                        price = float(trade.get("p", 0.0))
                        bid = float(quote.get("bp", 0.0))
                        ask = float(quote.get("ap", 0.0))

                        # Match Polygon's expected schema (using 'close' as current price)
                        rows.append(
                            {
                                "symbol": sym.replace("/USD", ""),
                                "timestamp": datetime.now(timezone.utc),
                                "close": price,  # Important: strategies look for 'close'
                                "price": price,  # Keep 'price' for backwards compat
                                "open": float(daily.get("o", 0.0)),
                                "high": float(daily.get("h", 0.0)),
                                "low": float(daily.get("l", 0.0)),
                                "volume": float(daily.get("v", 0.0)),
                                "vwap": float(daily.get("vw", 0.0)),
                                "bid_estimate": bid,
                                "ask_estimate": ask,
                                "mid_price": (bid + ask) / 2
                                if (bid and ask)
                                else price,
                            }
                        )

                    if rows:
                        return pl.DataFrame(rows)

        return pl.DataFrame()

    async def _fetch_stock_bars(
        self, session, symbols, start_date, end_date, timeframe
    ):
        url = f"{self.STOCKS_BASE_URL}/bars"
        params = {
            "symbols": ",".join(symbols),
            "timeframe": self._convert_timeframe(timeframe),
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "limit": 10000,
        }
        return await self._fetch_bars(session, url, params)

    async def _fetch_crypto_bars(
        self, session, symbols, start_date, end_date, timeframe
    ):
        url = f"{self.CRYPTO_BASE_URL}/bars"
        norm_symbols = self._normalize_crypto_symbols(symbols)
        params = {
            "symbols": ",".join(norm_symbols),
            "timeframe": self._convert_timeframe(timeframe),
            "start": start_date.strftime("%Y-%m-%dT00:00:00Z"),
            "end": end_date.strftime("%Y-%m-%dT23:59:59Z"),
            "limit": 10000,
        }
        return await self._fetch_bars(session, url, params)

    async def _fetch_bars(self, session, url, params):
        all_data = []
        while True:
            async with session.get(
                url, headers=self.headers, params=params
            ) as response:
                if response.status != 200:
                    logger.error(f"Error fetching data: {response.status}, url={url}")
                    break

                data = await response.json()
                bars = data.get("bars", {})

                for symbol, symbol_bars in bars.items():
                    if not symbol_bars:
                        continue

                    df = pl.DataFrame(symbol_bars)
                    clean_sym = symbol.replace("/USD", "")
                    df = df.with_columns(pl.lit(clean_sym).alias("symbol"))

                    # Rename columns
                    rename_map = {
                        "t": "timestamp",
                        "o": "open",
                        "h": "high",
                        "l": "low",
                        "c": "close",
                        "v": "volume",
                        "vw": "vwap",
                    }

                    # Only rename what exists
                    valid_renames = {
                        k: v for k, v in rename_map.items() if k in df.columns
                    }
                    df = df.rename(valid_renames)

                    # Ensure vwap exists and calculate if missing or zero
                    if "vwap" not in df.columns:
                        # Estimate VWAP using Typical Price as fallback
                        df = df.with_columns(
                            (
                                (pl.col("high") + pl.col("low") + pl.col("close")) / 3
                            ).alias("vwap")
                        )
                    else:
                        # If vwap exists but is 0 (often happens with some crypto feeds), recalculate
                        df = df.with_columns(
                            pl.when(pl.col("vwap") == 0)
                            .then(
                                (pl.col("high") + pl.col("low") + pl.col("close")) / 3
                            )
                            .otherwise(pl.col("vwap"))
                            .alias("vwap")
                        )

                    # Handle timestamp
                    if "timestamp" in df.columns and df["timestamp"].dtype == pl.Utf8:
                        df = df.with_columns(
                            pl.col("timestamp")
                            .str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%SZ")
                            .dt.convert_time_zone("UTC")
                        )

                    # Select safely
                    available_cols = df.columns
                    desired = [
                        "timestamp",
                        "open",
                        "high",
                        "low",
                        "close",
                        "volume",
                        "vwap",
                        "symbol",
                    ]
                    df = df.select([c for c in desired if c in available_cols])
                    all_data.append(df)

                if "next_page_token" in data and data["next_page_token"]:
                    params["page_token"] = data["next_page_token"]
                else:
                    break
        return all_data

    def _convert_timeframe(self, timeframe: str) -> str:
        tf = timeframe.upper().strip()
        mapping = TIMEFRAME_MAPPINGS.get(tf)
        if mapping and "alpaca" in mapping:
            return mapping["alpaca"]
        return "1Day"


class PolygonProvider(BaseDataProvider):
    """Polygon.io data provider"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.polygon.io"

    def get_provider_name(self) -> str:
        return "polygon"

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime, timeframe: str
    ) -> pl.DataFrame:
        """
        Get historical data from Polygon
        Args:
            symbol: str
            start_date: datetime
            end_date: datetime
            timeframe: str
        Returns:
            pl.DataFrame
        Raises:
            ValueError: If the symbol is not a valid crypto or stock asset on Polygon
        """
        timespan_multiplier = TIMEFRAME_MAPPINGS[timeframe].get("polygon")
        if timespan_multiplier is None:
            raise ValueError(f"Timeframe {timeframe} is not supported by Polygon")
        else:
            timespan = timespan_multiplier[0]
            multiplier = timespan_multiplier[1]

        if symbol not in AVAILABLE_CRYPTO_ASSETS:
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
        else:
            crypto_symbol = "X:" + symbol + "USD"
            logger.info(f"Data Provider: Polygon: Crypto symbol: {crypto_symbol}")
            url = f"{self.base_url}/v2/aggs/ticker/{crypto_symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"

        params = {
            "apiKey": self.api_key,
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if response.status == 200:
                    logger.info(f"Data Provider: Polygon Response: {response.status}")
                else:
                    logger.warning(
                        f"Polygon bar for {symbol}: Status {response.status}"
                    )
                    logger.error(f"Data Provider: Polygon Response: {data}")

                if "results" in data and data["results"]:
                    df = pl.DataFrame(data["results"])
                    logger.info(f"Polygon data for {symbol}: {df.to_dicts()}")

                    # Convert timestamp to datetime
                    df = df.with_columns(
                        pl.from_epoch("t", time_unit="ms")
                        .dt.convert_time_zone("America/New_York")
                        .alias("t")
                    )

                    # Rename columns
                    df = df.rename(
                        {
                            "o": "open",
                            "h": "high",
                            "l": "low",
                            "c": "close",
                            "v": "volume",
                            "vw": "vwap",
                        }
                    )

                    return df[["t", "open", "high", "low", "close", "volume", "vwap"]]
                else:
                    return pl.DataFrame()

    def _create_empty_bar_record(self, symbol: str) -> Dict[str, Any]:
        """Create an empty bar record for symbols with no data"""
        return {
            "symbol": symbol,
            "timestamp": 0,
            "open": 0.0,
            "high": 0.0,
            "low": 0.0,
            "close": 0.0,
            "volume": 0.0,
            "vwap": 0.0,
            "transactions": 0,
            "bid_estimate": 0.0,
            "ask_estimate": 0.0,
            "last_updated_utc": datetime.now().isoformat(),
        }

    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        """
        Get crypto quotes from Polygon using the latest 1-minute bars.
        This provides near real-time OHLCV data which is more comprehensive than quotes.

        Args:
            symbols: List of crypto symbols (e.g., ['BTC', 'ETH', 'SOL'])
                    Note: These should be base currency symbols, USD will be appended

        Returns:
            pl.DataFrame with columns: [symbol, timestamp, open, high, low, close,
                                    volume, vwap, transactions, bid_estimate, ask_estimate]
            Returns empty DataFrame if no data found or errors occur

        Raises:
            ValueError: If any symbol is not in AVAILABLE_CRYPTO_ASSETS
        """
        # Validate all symbols first
        for symbol in symbols:
            if symbol not in AVAILABLE_CRYPTO_ASSETS:
                raise ValueError(
                    f"Symbol {symbol} is not a tradable crypto asset on Polygon"
                )

        if not symbols:
            logger.warning("No symbols provided to get_crypto_quote")
            return pl.DataFrame()

        # Calculate time range for latest bars (last 2 minutes to ensure we get data)
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=2)

        # Format dates for API
        from_date = start_time.strftime("%Y-%m-%d")
        to_date = end_time.strftime("%Y-%m-%d")

        async with aiohttp.ClientSession() as session:
            all_bars = []

            # Use semaphore to limit concurrent requests (respect rate limits)
            semaphore = asyncio.Semaphore(5)

            async def fetch_symbol_bar(symbol: str):
                async with semaphore:
                    try:
                        # Polygon crypto format: X:SYMBOLUSD
                        crypto_ticker = f"X:{symbol}USD"

                        # Get latest 1-minute bars for near real-time data
                        url = f"{self.base_url}/v2/aggs/ticker/{crypto_ticker}/range/1/minute/{from_date}/{to_date}"
                        params = {
                            "apikey": self.api_key,
                            "adjusted": "true",
                            "sort": "desc",  # Get latest bars first
                            "limit": 1,  # Only need the most recent bar
                        }

                        async with session.get(url, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.info(
                                    f"Polygon crypto bar for {symbol}: Status {response.status}"
                                )

                                if "results" in data and data["results"]:
                                    # Get the most recent bar (first one due to desc sort)
                                    latest_bar = data["results"][0]

                                    # Parse bar data
                                    bar_record = {
                                        "symbol": symbol,
                                        "timestamp": latest_bar.get(
                                            "t", 0
                                        ),  # Unix timestamp in ms
                                        "open": latest_bar.get("o", 0.0),
                                        "high": latest_bar.get("h", 0.0),
                                        "low": latest_bar.get("l", 0.0),
                                        "close": latest_bar.get(
                                            "c", 0.0
                                        ),  # This is our "current price"
                                        "volume": latest_bar.get("v", 0.0),
                                        "vwap": latest_bar.get(
                                            "vw", 0.0
                                        ),  # Volume weighted average price
                                        "transactions": latest_bar.get(
                                            "n", 0
                                        ),  # Number of transactions
                                        "last_updated_utc": datetime.now().isoformat(),
                                    }

                                    # Estimate bid/ask from OHLC (common practice)
                                    # Bid = slightly below close, Ask = slightly above close
                                    close_price = bar_record["close"]
                                    if close_price > 0:
                                        spread_estimate = (
                                            close_price * 0.001
                                        )  # 0.1% spread estimate
                                        bar_record["bid_estimate"] = close_price - (
                                            spread_estimate / 2
                                        )
                                        bar_record["ask_estimate"] = close_price + (
                                            spread_estimate / 2
                                        )
                                    else:
                                        bar_record["bid_estimate"] = 0.0
                                        bar_record["ask_estimate"] = 0.0

                                    return bar_record

                                else:
                                    logger.warning(f"No bar data found for {symbol}")
                                    logger.warning(
                                        f"Polygon crypto bar for {symbol}: Status {response.status}"
                                    )
                                    return self._create_empty_bar_record(symbol)

                            elif response.status == 401:
                                logger.error(
                                    "Polygon API authentication failed - check API key"
                                )
                                return None

                            elif response.status == 403:
                                logger.error(
                                    "Polygon API access forbidden - check subscription plan"
                                )
                                return None

                            elif response.status == 429:
                                logger.error(
                                    f"Polygon API rate limit exceeded for {symbol}"
                                )
                                # Return empty record rather than None to continue processing
                                return self._create_empty_bar_record(symbol)

                            elif response.status == 404:
                                logger.warning(
                                    f"No data found for crypto symbol {symbol}"
                                )
                                return self._create_empty_bar_record(symbol)

                            else:
                                logger.error(
                                    f"Polygon API error for {symbol}: Status {response.status}"
                                )
                                response_text = await response.text()
                                logger.error(f"Response: {response_text}")
                                return self._create_empty_bar_record(symbol)

                    except aiohttp.ClientError as e:
                        logger.error(f"Network error fetching bar for {symbol}: {e}")
                        return self._create_empty_bar_record(symbol)

                    except Exception as e:
                        logger.error(f"Unexpected error fetching bar for {symbol}: {e}")
                        return self._create_empty_bar_record(symbol)

            # Execute all requests concurrently
            tasks = [fetch_symbol_bar(symbol) for symbol in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out None results and exceptions
            for result in results:
                if result is not None and not isinstance(result, Exception):
                    all_bars.append(result)

            # Convert to Polars DataFrame
            if not all_bars:
                logger.warning("No crypto bars retrieved from Polygon")
                return pl.DataFrame()

            try:
                df = pl.DataFrame(all_bars)

                # Convert timestamp and ensure proper data types
                df = df.with_columns(
                    [
                        # Convert timestamp from milliseconds to datetime
                        pl.when(pl.col("timestamp") > 0)
                        .then(
                            pl.from_epoch(
                                "timestamp", time_unit="ms"
                            ).dt.convert_time_zone("UTC")
                        )
                        .otherwise(pl.lit(None).cast(pl.Datetime))
                        .alias("timestamp"),
                        # Ensure numeric columns are proper types
                        pl.col("open").cast(pl.Float64),
                        pl.col("high").cast(pl.Float64),
                        pl.col("low").cast(pl.Float64),
                        pl.col("close").cast(pl.Float64),
                        pl.col("volume").cast(pl.Float64),
                        pl.col("vwap").cast(pl.Float64),
                        pl.col("transactions").cast(pl.Int32),
                        pl.col("bid_estimate").cast(pl.Float64),
                        pl.col("ask_estimate").cast(pl.Float64),
                    ]
                )

                # Add additional calculated fields for compatibility
                df = df.with_columns(
                    [
                        # Mid price (same as close for bars)
                        pl.col("close").alias("mid_price"),
                        # Price change from open to close
                        pl.when(pl.col("open") > 0)
                        .then(pl.col("close") - pl.col("open"))
                        .otherwise(0.0)
                        .alias("price_change"),
                        # Percentage change
                        pl.when(pl.col("open") > 0)
                        .then(
                            ((pl.col("close") - pl.col("open")) / pl.col("open")) * 100
                        )
                        .otherwise(0.0)
                        .alias("price_change_percent"),
                        # Trading intensity (volume per transaction)
                        pl.when(pl.col("transactions") > 0)
                        .then(pl.col("volume") / pl.col("transactions"))
                        .otherwise(0.0)
                        .alias("avg_trade_size"),
                    ]
                )

                # Select and order columns for final output
                final_columns = [
                    "symbol",
                    "timestamp",
                    "close",
                    "open",
                    "high",
                    "low",
                    "volume",
                    "vwap",
                    "transactions",
                    "bid_estimate",
                    "ask_estimate",
                    "mid_price",
                    "price_change",
                    "price_change_percent",
                    "avg_trade_size",
                    "last_updated_utc",
                ]

                # Filter columns that exist in the DataFrame
                existing_columns = [col for col in final_columns if col in df.columns]

                return df.select(existing_columns)

            except Exception as e:
                logger.error(f"Error creating DataFrame from crypto bars: {e}")
                return pl.DataFrame()

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Polygon using latest 1-minute bar"""
        async with aiohttp.ClientSession() as session:
            # Get the most recent 1-minute bar (last 2 minutes to ensure data)
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(minutes=2)).strftime("%Y-%m-%d")

            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
            params = {
                "apikey": self.api_key,
                "adjusted": "true",
                "sort": "desc",
                "limit": 1,
            }

            async with session.get(url, params=params) as response:
                data = await response.json()

                if "results" in data and data["results"]:
                    bar = data["results"][0]  # Most recent bar
                    close_price = bar.get("c", 0)

                    # Simple bid/ask estimation from close price
                    spread = close_price * 0.001  # 0.1% spread estimate
                    bid_price = close_price - (spread / 2)
                    ask_price = close_price + (spread / 2)

                    return {
                        "symbol": symbol,
                        "price": close_price,
                        "bid": bid_price,
                        "ask": ask_price,
                        "volume": bar.get("v", 0),
                        "timestamp": pl.from_epoch(bar.get("t", 0), time_unit="ms"),
                    }
                else:
                    return {}


class DataProviderFactory:
    """Factory class to create data providers"""

    @staticmethod
    def get_provider(provider_name: str, **kwargs) -> BaseDataProvider:
        """Get a data provider instance"""
        provider_name = provider_name.lower()

        if provider_name == "yahoo":
            return YahooFinanceProvider()

        elif provider_name == "alpaca":
            if "api_key" not in kwargs or "secret_key" not in kwargs:
                raise ValueError("Alpaca provider requires api_key and secret_key")
            return AlpacaProvider(
                api_key=kwargs["api_key"],
                secret_key=kwargs["secret_key"],
                base_url=kwargs.get("base_url", "https://data.alpaca.markets"),
            )

        elif provider_name == "polygon":
            if "api_key" not in kwargs:
                raise ValueError("Polygon provider requires api_key")
            return PolygonProvider(api_key=kwargs["api_key"])

        else:
            raise ValueError(f"Unknown data provider: {provider_name}")

    @staticmethod
    def get_supported_timeframes(provider_name: str = None) -> Dict[str, list]:
        """Get supported timeframes for a specific provider or all providers"""
        if provider_name:
            provider_name = provider_name.lower()
            if provider_name not in ["yahoo", "alpaca", "polygon"]:
                raise ValueError(f"Unknown provider: {provider_name}")

            supported = []
            for timeframe, mappings in TIMEFRAME_MAPPINGS.items():
                if mappings.get(provider_name) is not None:
                    supported.append(timeframe)
            return {provider_name: supported}
        else:
            # Return all supported timeframes for each provider
            result = {"yahoo": [], "alpaca": [], "polygon": []}
            for timeframe, mappings in TIMEFRAME_MAPPINGS.items():
                for provider in result.keys():
                    if mappings.get(provider) is not None:
                        result[provider].append(timeframe)
            return result
