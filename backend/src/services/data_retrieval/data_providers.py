# backend/src/services/data_providers.py
from abc import ABC, abstractmethod
import polars as pl
from datetime import datetime, timedelta
import logging
from typing import Optional, Dict, Any, Tuple, Union, List
import yfinance as yf
import aiohttp
from urllib.parse import urlencode
import asyncio
import pandas as pd

logger = logging.getLogger(__name__)

TIMEFRAME_MAPPINGS = {
    '1MIN': {'yahoo': '1m', 'alpaca': '1Min', 'polygon': ('minute', 1)},
    '2MIN': {'yahoo': '2m', 'alpaca': '2Min', 'polygon': ('minute', 2)},
    '5MIN': {'yahoo': '5m', 'alpaca': '5Min', 'polygon': ('minute', 5)},
    '15MIN': {'yahoo': '15m', 'alpaca': '15Min', 'polygon': ('minute', 15)},
    '30MIN': {'yahoo': '30m', 'alpaca': '30Min', 'polygon': ('minute', 30)},
    '60MIN': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1HOUR': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1H': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1d': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '1D': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '2D': {'yahoo': '2d', 'alpaca': '2Day', 'polygon': ('day', 2)},
    '5D': {'yahoo': '5d', 'alpaca': '5Day', 'polygon': ('day', 5)},
    '1wk': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1w': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1W': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1mo': {'yahoo': '1mo', 'alpaca': '1Month', 'polygon': ('month', 1)},
    '3mo': {'yahoo': '3mo', 'alpaca': '3Month', 'polygon': ('month', 3)},
}

AVAILABLE_CRYPTO_ASSETS = ['AAVE',
                            'AVAX',
                            'BAT',
                            'BCH',
                            'BTC',
                            'CRV',
                            'DOGE',
                            'DOT',
                            'ETH',
                            'GRT',
                            'LINK',
                            'LTC',
                            'MKR',
                            'PEPE',
                            'SHIB',
                            'SOL',
                            'SUSHI',
                            'TRUMP',
                            'UNI',
                            'USDC',
                            'USDG',
                            'USDT',
                            'XRP',
                            'XTZ',
                            'YFI']

ALPACA_RESPONSE_CODES = {
    200: "Success",
    400: """One of the request parameters is invalid. See the returned message for details.""",
    403: """Authentication headers are missing or invalid. 
    Make sure you authenticate your request with a valid API key.""",
    429: """Too many requests. You hit the rate limit. 
    Use the X-RateLimit-... response headers to make sure you're under the rate limit.""",
    500: """Internal server error. We recommend retrying these later. 
    If the issue persists, please contact us on Slack or on the Community Forum."""
}

class BaseDataProvider(ABC):
    """Abstract base class for data providers"""
    
    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pl.DataFrame:
        """Get historical OHLCV data"""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol"""
        pass
    
    @abstractmethod
    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        """Get crypto quote from Alpaca"""
        pass
    
    def get_provider_timeframe(self, timeframe: str) -> Union[str, Tuple[str, int], None]:
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
        return 'yahoo'
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pl.DataFrame:
        """Get historical data from Yahoo Finance"""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def fetch_data():
            ticker = yf.Ticker(symbol)
            interval = self.get_provider_timeframe(timeframe) or '1d'
            
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval,
                auto_adjust=True
            )
            
            # Rename columns to lowercase
            df.columns = df.columns.str.lower()
            
            # Ensure we have all required columns
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in df.columns:
                    df[col] = 0
            
            logger.info(f"Yahoo Finance data for {symbol}: {df.to_json(orient='records')}")
            return df
        
        return await loop.run_in_executor(None, fetch_data)
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Yahoo Finance"""
        loop = asyncio.get_event_loop()
        
        def fetch_quote():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return {
                'symbol': symbol,
                'price': info.get('regularMarketPrice', 0),
                'bid': info.get('bid', 0),
                'ask': info.get('ask', 0),
                'volume': info.get('regularMarketVolume', 0),
                'timestamp': datetime.now()
            }
        
        return await loop.run_in_executor(None, fetch_quote)

class AlpacaProvider(BaseDataProvider):
    """Alpaca Markets data provider"""
    
    def __init__(self, api_key: str, secret_key: str, base_url: str = 'https://data.alpaca.markets/v2'):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }
    
    def get_provider_name(self) -> str:
        return 'alpaca'
    
    async def get_historical_data(self,
                                  symbols: List[str],
                                  start_date: datetime,
                                  end_date: datetime,
                                  timeframe: str
                                  ) -> pl.DataFrame:
        """
        Fetches historical bar data for multiple symbols from Alpaca, handling pagination.

        Args:
            symbols: A list of stock symbols.
            start_date: The start date for the historical data.
            end_date: The end date for the historical data.
            timeframe: The timeframe for the bars (e.g., '1D', '1H', '1Min').

        Returns:
            A Polars DataFrame containing the historical data with a 'symbol' column.
            Returns an empty DataFrame if no data is found or an error occurs.
        """

        timeframe_str = TIMEFRAME_MAPPINGS[timeframe].get('alpaca')
        logger.info(f"DEBUG: Data Provider: Alpaca: Timeframe: {timeframe_str}")
        async with aiohttp.ClientSession() as session:
            stocks_url = f"{self.base_url}/v2/stocks/bars"
            crypto_url = f"{self.base_url}/v1beta3/crypto/us/bars"
            
            crypto_symbols = []
            stocks_symbols = []
            
            logger.info(f"DEBUG: ALPACA_PROVIDER: Symbols: {symbols}, type: {type(symbols)}")

            for symbol in symbols:
                logger.info(f"DEBUG: Individual Symbols ALPACA_PROVIDER: Symbol: {symbol}, type: {type(symbol)}")
                if symbol.upper() in AVAILABLE_CRYPTO_ASSETS:

                    crypto_symbols = [f"{symbol}/USD" for symbol in symbols]
                else:
                    stocks_symbols.append(symbol)

            logger.info(f"DEBUG: ALPACA_PROVIDER: Crypto symbols: {crypto_symbols}")
            logger.info(f"DEBUG: ALPACA_PROVIDER: Stocks symbols: {stocks_symbols}")
            
            
            all_bars = []
            # Fetch stocks data
            if len(stocks_symbols) > 0:
                params = {
                    'symbols': ','.join(stocks_symbols),
                    'timeframe': timeframe_str,
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'limit': 10000
                }
                
                page_token = None
                while True:
                    async with session.get(stocks_url, headers=self.headers, params=params) as response:
                        response.raise_for_status()

                        if response.status == 200:
                            data = await response.json()
                            bars_data = data.get('bars')
                            if bars_data:
                                for symbol, symbol_bars in bars_data.items():
                                    for bar in symbol_bars:
                                        bar['symbol'] = symbol
                                        all_bars.append(bar)
                            page_token = data.get('next_page_token')
                            if not page_token:
                                break
                            params['page_token'] = page_token
                        else:
                            logger.error(f"{ALPACA_RESPONSE_CODES[response.status]}")
                            return pl.DataFrame()
                    await asyncio.sleep(0.3)  # Added delay to avoid rate limiting

            # Fetch crypto data
            if len(crypto_symbols) > 0:
                params = {
                    'symbols': ','.join(crypto_symbols),
                    'timeframe': timeframe_str,
                    'start': start_date.strftime('%Y-%m-%d'),
                    'end': end_date.strftime('%Y-%m-%d'),
                    'limit': 10000
                }

                page_token = None
                while True:
                    async with session.get(crypto_url, headers=self.headers, params=params) as response:
                        response.raise_for_status()
                        if response.status == 200:
                            data = await response.json()
                            crypto_bars_data = data.get('bars')
                            if crypto_bars_data:
                                for crypto_symbol, crypto_symbol_bars in crypto_bars_data.items():
                                    for bar in crypto_symbol_bars:
                                        bar['symbol'] = crypto_symbol.rstrip('/USD')
                                        all_bars.append(bar)
                            page_token = data.get('next_page_token')
                            if not page_token:
                                break
                            params['page_token'] = page_token
                        else:
                            logger.warning(f"Alpaca bar for {symbol}: Status {response.status}")
                            logger.error(f"{ALPACA_RESPONSE_CODES[response.status]}")
                            return pl.DataFrame()
                    await asyncio.sleep(0.3)  # Added delay to avoid rate limiting

            df = pl.DataFrame(all_bars)

            if not df.is_empty():
                #logger.info(f"Alpaca data for {symbols}: {df.to_dicts()}")
                df = df.with_columns(
                    pl.col("t").str.to_datetime(format="%Y-%m-%dT%H:%M:%S%.fZ", time_zone="America/New_York").alias("timestamp")
                ).rename({
                'o': 'open',
                'h': 'high',
                'l': 'low',
                'c': 'close',
                'v': 'volume',
                'vw': 'vwap'
            })
            # Ensure all required columns are present before selecting
            required_cols = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap']
            # Filter out columns that are not in the DataFrame
            existing_cols = [col for col in required_cols if col in df.columns]
            logger.info(f"DEBUG: ALPACA_PROVIDER: Existing columns: {df.head(10)}")
            
            return df.select(existing_cols)
        
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Alpaca"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/v2/stocks/{symbol}/quotes/latest"
            
            async with session.get(url, headers=self.headers) as response:
                data = await response.json()
                
                if 'quote' in data:
                    quote = data['quote']
                    return {
                        'symbol': symbol,
                        'price': quote.get('ap', 0),  # ask price
                        'bid': quote.get('bp', 0),     # bid price
                        'ask': quote.get('ap', 0),     # ask price
                        'volume': quote.get('as', 0),  # ask size
                        'timestamp': pl.to_datetime(quote.get('t'))
                    }
                else:
                    return {}

    async def get_asset_list(self):
        """Get list of assets from Alpaca"""
        async with aiohttp.ClientSession() as session:
            url = "https://paper-api.alpaca.markets/v2/assets"
            async with session.get(url, headers=self.headers) as response:
                data = await response.json()
                return data

    async def get_crypto_quote(self, symbols: list[str]) -> pl.DataFrame:
        """Get crypto quote from Alpaca"""

        for symbol in symbols:
            if symbol not in AVAILABLE_CRYPTO_ASSETS:
                raise ValueError(f"Symbol {symbol} is not a tradable crypto asset on Alpaca")

        symbols = ['/USD'.join(x) for x in symbols]

        async with aiohttp.ClientSession() as session:
            base_url = "https://data.alpaca.markets/v1beta3/crypto/us/latest/bars"
            params = {
                'symbols': symbols
            }
            async with session.get(base_url, params=params) as response:
                data = await response.json()
                data = pl.DataFrame(data['bars'])
                return data

class PolygonProvider(BaseDataProvider):
    """Polygon.io data provider"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = 'https://api.polygon.io'
    
    def get_provider_name(self) -> str:
        return 'polygon'
    
    async def get_historical_data(self,
                                  symbol: str,
                                  start_date: datetime,
                                  end_date: datetime,
                                  timeframe: str
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
        timespan_multiplier = TIMEFRAME_MAPPINGS[timeframe].get('polygon')
        if timespan_multiplier is None:
            raise ValueError(f"Timeframe {timeframe} is not supported by Polygon")
        else:
            timespan = timespan_multiplier[0]
            multiplier = timespan_multiplier[1]


        if symbol not in AVAILABLE_CRYPTO_ASSETS:
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"
        else:
            crypto_symbol = 'X:' + symbol + 'USD'
            logger.info(f"Data Provider: Polygon: Crypto symbol: {crypto_symbol}")
            url = f"{self.base_url}/v2/aggs/ticker/{crypto_symbol}/range/{multiplier}/{timespan}/{start_date}/{end_date}"

        params = {
            'apiKey': self.api_key,
            'adjusted': 'true',
            'sort': 'asc',
            'limit': 50000
        }


        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if response.status == 200:      
                    logger.info(f"Data Provider: Polygon Response: {response.status}")
                else:
                    logger.warning(f"Polygon bar for {symbol}: Status {response.status}")
                    logger.error(f"Data Provider: Polygon Response: {data}")

                if 'results' in data and data['results']:
                    df = pl.DataFrame(data['results'])
                    logger.info(f"Polygon data for {symbol}: {df.to_dicts()}")
                    
                    # Convert timestamp to datetime
                    df = df.with_columns(
                        pl.from_epoch('t', time_unit='ms').dt.convert_time_zone("America/New_York").alias("t")
                    )
                    
                    # Rename columns
                    df = df.rename({
                        'o': 'open',
                        'h': 'high',
                        'l': 'low',
                        'c': 'close',
                        'v': 'volume',
                        'vw': 'vwap'
                    })
                    
                    return df[['t', 'open', 'high', 'low', 'close', 'volume', 'vwap']]
                else:
                    return pl.DataFrame()
                
    def _create_empty_bar_record(self, symbol: str) -> Dict[str, Any]:
        """Create an empty bar record for symbols with no data"""
        return {
            'symbol': symbol,
            'timestamp': 0,
            'open': 0.0,
            'high': 0.0,
            'low': 0.0,
            'close': 0.0,
            'volume': 0.0,
            'vwap': 0.0,
            'transactions': 0,
            'bid_estimate': 0.0,
            'ask_estimate': 0.0,
            'last_updated_utc': datetime.now().isoformat()
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
                raise ValueError(f"Symbol {symbol} is not a tradable crypto asset on Polygon")
        
        if not symbols:
            logger.warning("No symbols provided to get_crypto_quote")
            return pl.DataFrame()
        
        # Calculate time range for latest bars (last 2 minutes to ensure we get data)
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=2)
        
        # Format dates for API
        from_date = start_time.strftime('%Y-%m-%d')
        to_date = end_time.strftime('%Y-%m-%d')
        
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
                            'apikey': self.api_key,
                            'adjusted': 'true',
                            'sort': 'desc',  # Get latest bars first
                            'limit': 1       # Only need the most recent bar
                        }
                        
                        async with session.get(url, params=params) as response:
                            if response.status == 200:
                                data = await response.json()
                                logger.info(f"Polygon crypto bar for {symbol}: Status {response.status}")
                                
                                if 'results' in data and data['results']:
                                    # Get the most recent bar (first one due to desc sort)
                                    latest_bar = data['results'][0]
                                    
                                    # Parse bar data
                                    bar_record = {
                                        'symbol': symbol,
                                        'timestamp': latest_bar.get('t', 0),  # Unix timestamp in ms
                                        'open': latest_bar.get('o', 0.0),
                                        'high': latest_bar.get('h', 0.0),
                                        'low': latest_bar.get('l', 0.0),
                                        'close': latest_bar.get('c', 0.0),     # This is our "current price"
                                        'volume': latest_bar.get('v', 0.0),
                                        'vwap': latest_bar.get('vw', 0.0),     # Volume weighted average price
                                        'transactions': latest_bar.get('n', 0), # Number of transactions
                                        'last_updated_utc': datetime.now().isoformat()
                                    }
                                    
                                    # Estimate bid/ask from OHLC (common practice)
                                    # Bid = slightly below close, Ask = slightly above close
                                    close_price = bar_record['close']
                                    if close_price > 0:
                                        spread_estimate = close_price * 0.001  # 0.1% spread estimate
                                        bar_record['bid_estimate'] = close_price - (spread_estimate / 2)
                                        bar_record['ask_estimate'] = close_price + (spread_estimate / 2)
                                    else:
                                        bar_record['bid_estimate'] = 0.0
                                        bar_record['ask_estimate'] = 0.0
                                    
                                    return bar_record
                                
                                else:
                                    logger.warning(f"No bar data found for {symbol}")
                                    logger.warning(f"Polygon crypto bar for {symbol}: Status {response.status}")
                                    return self._create_empty_bar_record(symbol)
                            
                            elif response.status == 401:
                                logger.error("Polygon API authentication failed - check API key")
                                return None
                            
                            elif response.status == 403:
                                logger.error("Polygon API access forbidden - check subscription plan")
                                return None
                            
                            elif response.status == 429:
                                logger.error(f"Polygon API rate limit exceeded for {symbol}")
                                # Return empty record rather than None to continue processing
                                return self._create_empty_bar_record(symbol)
                            
                            elif response.status == 404:
                                logger.warning(f"No data found for crypto symbol {symbol}")
                                return self._create_empty_bar_record(symbol)
                            
                            else:
                                logger.error(f"Polygon API error for {symbol}: Status {response.status}")
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
                df = df.with_columns([
                    # Convert timestamp from milliseconds to datetime
                    pl.when(pl.col("timestamp") > 0)
                    .then(pl.from_epoch("timestamp", time_unit="ms").dt.convert_time_zone("UTC"))
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
                ])
                
                # Add additional calculated fields for compatibility
                df = df.with_columns([
                    # Mid price (same as close for bars)
                    pl.col("close").alias("mid_price"),
                    
                    # Price change from open to close
                    pl.when(pl.col("open") > 0)
                    .then(pl.col("close") - pl.col("open"))
                    .otherwise(0.0)
                    .alias("price_change"),
                    
                    # Percentage change
                    pl.when(pl.col("open") > 0)
                    .then(((pl.col("close") - pl.col("open")) / pl.col("open")) * 100)
                    .otherwise(0.0)
                    .alias("price_change_percent"),
                    
                    # Trading intensity (volume per transaction)
                    pl.when(pl.col("transactions") > 0)
                    .then(pl.col("volume") / pl.col("transactions"))
                    .otherwise(0.0)
                    .alias("avg_trade_size")
                ])
                
                # Select and order columns for final output
                final_columns = [
                    'symbol', 'timestamp', 'close', 'open', 'high', 'low', 
                    'volume', 'vwap', 'transactions', 'bid_estimate', 'ask_estimate',
                    'mid_price', 'price_change', 'price_change_percent', 'avg_trade_size',
                    'last_updated_utc'
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
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(minutes=2)).strftime('%Y-%m-%d')
            
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
            params = {
                'apikey': self.api_key,
                'adjusted': 'true',
                'sort': 'desc',
                'limit': 1
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'results' in data and data['results']:
                    bar = data['results'][0]  # Most recent bar
                    close_price = bar.get('c', 0)
                    
                    # Simple bid/ask estimation from close price
                    spread = close_price * 0.001  # 0.1% spread estimate
                    bid_price = close_price - (spread / 2)
                    ask_price = close_price + (spread / 2)
                    
                    return {
                        'symbol': symbol,
                        'price': close_price,
                        'bid': bid_price,
                        'ask': ask_price,
                        'volume': bar.get('v', 0),
                        'timestamp': pl.from_epoch(bar.get('t', 0), time_unit='ms')
                    }
                else:
                    return {}
                

class DataProviderFactory:
    """Factory class to create data providers"""
    
    @staticmethod
    def get_provider(
        provider_name: str,
        **kwargs
    ) -> BaseDataProvider:
        """Get a data provider instance"""
        provider_name = provider_name.lower()
        
        if provider_name == 'yahoo':
            return YahooFinanceProvider()
        
        elif provider_name == 'alpaca':
            if 'api_key' not in kwargs or 'secret_key' not in kwargs:
                raise ValueError("Alpaca provider requires api_key and secret_key")
            return AlpacaProvider(
                api_key=kwargs['api_key'],
                secret_key=kwargs['secret_key'],
                base_url=kwargs.get('base_url', 'https://data.alpaca.markets')
            )
        
        elif provider_name == 'polygon':
            if 'api_key' not in kwargs:
                raise ValueError("Polygon provider requires api_key")
            return PolygonProvider(api_key=kwargs['api_key'])
        
        else:
            raise ValueError(f"Unknown data provider: {provider_name}")
    
    @staticmethod
    def get_supported_timeframes(provider_name: str = None) -> Dict[str, list]:
        """Get supported timeframes for a specific provider or all providers"""
        if provider_name:
            provider_name = provider_name.lower()
            if provider_name not in ['yahoo', 'alpaca', 'polygon']:
                raise ValueError(f"Unknown provider: {provider_name}")
            
            supported = []
            for timeframe, mappings in TIMEFRAME_MAPPINGS.items():
                if mappings.get(provider_name) is not None:
                    supported.append(timeframe)
            return {provider_name: supported}
        else:
            # Return all supported timeframes for each provider
            result = {'yahoo': [], 'alpaca': [], 'polygon': []}
            for timeframe, mappings in TIMEFRAME_MAPPINGS.items():
                for provider in result.keys():
                    if mappings.get(provider) is not None:
                        result[provider].append(timeframe)
            return result