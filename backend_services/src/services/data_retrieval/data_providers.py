# backend/src/services/data_providers.py
from abc import ABC, abstractmethod
import polars as pl
from datetime import datetime
import logging
from typing import Optional, Dict, Any, Tuple, Union, List
import yfinance as yf
import aiohttp
import asyncio
import pandas as pd

logger = logging.getLogger(__name__)

# Consolidated timeframe mappings
TIMEFRAME_MAPPINGS = {
    # Standard input timeframes (what users can specify)
    '1M': {'yahoo': '1m', 'alpaca': '1Min', 'polygon': ('minute', 1)},
    '2M': {'yahoo': '2m', 'alpaca': None, 'polygon': ('minute', 2)},
    '5M': {'yahoo': '5m', 'alpaca': '5Min', 'polygon': ('minute', 5)},
    '15M': {'yahoo': '15m', 'alpaca': '15Min', 'polygon': ('minute', 15)},
    '30M': {'yahoo': '30m', 'alpaca': '30Min', 'polygon': ('minute', 30)},
    '60M': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1H': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1d': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '1D': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '5D': {'yahoo': '5d', 'alpaca': None, 'polygon': ('day', 5)},
    '1wk': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1w': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1W': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1mo': {'yahoo': '1mo', 'alpaca': None, 'polygon': None},
    '3mo': {'yahoo': '3mo', 'alpaca': None, 'polygon': None},
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
        async with aiohttp.ClientSession() as session:
            timeframe_str = self.get_provider_timeframe(timeframe) or '1Day'
            url = f"{self.base_url}/v2/stocks/bars"
            
            params = {
                'symbols': ','.join(symbols),
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'timeframe': timeframe_str,
                'limit': 10000,
                'adjustment': 'raw'
            }
            
            all_bars = []
            page_token = None
            
            while True:
                if page_token:
                    params['page_token'] = page_token
                
                try:
                    async with session.get(url, headers=self.headers, params=params) as response:
                        response.raise_for_status()

                        if response.status == 200:
                            data = await response.json()
                        elif response.status == 400:
                            logger.error(f"Error fetching historical data from Alpaca: {response.body}")
                            return pl.DataFrame()
                        elif response.status == 403:
                            logger.error(f"""Authentication headers are missing or invalid. 
                                         Make sure you authenticate your request with a valid API key.""")
                            return pl.DataFrame()
                        elif response.status == 429:
                            logger.error(f"""Too many requests. You hit the rate limit. 
                                         Use the X-RateLimit-... 
                                         response headers to make sure you're under the rate limit.""")
                            return pl.DataFrame()
                        elif response.status == 500:
                            logger.error(f"""Internal server error. 
                                         We recommend retrying these later. 
                                         If the issue persists, please contact us 
                                         on Slack or on the Community Forum.""")
                            return pl.DataFrame()

                        bars_data = data.get('bars')
                        
                except aiohttp.ClientError as e:
                    logger.error(f"Error fetching historical data from Alpaca: {e}")
                    return pl.DataFrame()

                bars_data = data.get('bars')
                if bars_data:
                    for symbol, symbol_bars in bars_data.items():
                        for bar in symbol_bars:
                            bar['symbol'] = symbol
                            all_bars.append(bar)
                
                page_token = data.get('next_page_token')
                if not page_token:
                    break
            
            if not all_bars:
                return pl.DataFrame()

            df = pl.DataFrame(all_bars)

            df = df.with_columns(
                pl.col("t").str.to_datetime().alias("timestamp")
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
            crypto_symbol = symbol + 'USD'
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
                    logger.error(f"Data Provider: Polygon Response: {data}")

                if 'results' in data and data['results']:
                    df = pl.DataFrame(data['results'])
                    
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
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Polygon"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/v2/last/trade/{symbol}"
            params = {'apiKey': self.api_key}
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                logger.info(f"Data Provider: Polygon Quote Response: {data}")
                if 'results' in data:
                    result = data['results']
                    return {
                        'symbol': symbol,
                        'price': result.get('p', 0),
                        'bid': 0,  # Polygon doesn't provide bid/ask in this endpoint
                        'ask': 0,
                        'volume': result.get('s', 0),
                        'timestamp': pl.to_datetime(result.get('t'), unit='ns')
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