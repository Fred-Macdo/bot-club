# backend/src/services/data_providers.py
from abc import ABC, abstractmethod
import polars as pl
from datetime import datetime
import logging
from typing import Optional, Dict, Any, Tuple, Union
import yfinance as yf
import aiohttp
import asyncio
import pandas as pd

logger = logging.getLogger(__name__)

# Consolidated timeframe mappings
TIMEFRAME_MAPPINGS = {
    # Standard input timeframes (what users can specify)
    '1m': {'yahoo': '1m', 'alpaca': '1Min', 'polygon': ('minute', 1)},
    '2m': {'yahoo': '2m', 'alpaca': None, 'polygon': None},
    '5m': {'yahoo': '5m', 'alpaca': '5Min', 'polygon': ('minute', 5)},
    '15m': {'yahoo': '15m', 'alpaca': '15Min', 'polygon': ('minute', 15)},
    '30m': {'yahoo': '30m', 'alpaca': '30Min', 'polygon': ('minute', 30)},
    '60m': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1h': {'yahoo': '60m', 'alpaca': '1Hour', 'polygon': ('hour', 1)},
    '1d': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '1D': {'yahoo': '1d', 'alpaca': '1Day', 'polygon': ('day', 1)},
    '5d': {'yahoo': '5d', 'alpaca': None, 'polygon': None},
    '1wk': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1w': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1W': {'yahoo': '1wk', 'alpaca': '1Week', 'polygon': ('week', 1)},
    '1mo': {'yahoo': '1mo', 'alpaca': None, 'polygon': None},
    '3mo': {'yahoo': '3mo', 'alpaca': None, 'polygon': None},
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
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': secret_key
        }
    
    def get_provider_name(self) -> str:
        return 'alpaca'
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pl.DataFrame:
        """Get historical data from Alpaca"""
        async with aiohttp.ClientSession() as session:
            timeframe_str = self.get_provider_timeframe(timeframe) or '1Day'
            
            url = f"{self.base_url}/v2/stocks/{symbol}/bars"
            params = {
                'start': start_date.isoformat() + 'Z',
                'end': end_date.isoformat() + 'Z',
                'timeframe': timeframe_str,
                'limit': 10000
            }
            
            all_bars = []
            
            while True:
                # Only add page_token if it's not None
                if 'page_token' in params and params['page_token'] is None:
                    del params['page_token']
                
                async with session.get(url, headers=self.headers, params=params) as response:
                    data = await response.json()
                    #logger.info(f"Data Provider: Alpaca Response: {data}")
                    if 'bars' in data:
                        all_bars.extend(data['bars'])
                    
                    # Check if there's more data
                    if 'next_page_token' in data and data['next_page_token']:
                        params['page_token'] = data['next_page_token']
                    else:
                        break
            
            # Convert to DataFrame
            if all_bars:
                df = pl.DataFrame(all_bars)
                
                # Fix datetime parsing - Alpaca returns ISO format with 'Z' timezone
                df = df.with_columns(
                    pl.col("t").str.to_datetime("%Y-%m-%dT%H:%M:%SZ").dt.convert_time_zone("America/New_York").alias("t")
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
                return pd.DataFrame()
    
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

class PolygonProvider(BaseDataProvider):
    """Polygon.io data provider"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = 'https://api.polygon.io'
    
    def get_provider_name(self) -> str:
        return 'polygon'
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pl.DataFrame:
        """Get historical data from Polygon"""
        async with aiohttp.ClientSession() as session:
            timeframe_mapping = self.get_provider_timeframe(timeframe)
            if timeframe_mapping is None:
                timeunit, multiplier = ('day', 1)  # default fallback
            else:
                timeunit, multiplier = timeframe_mapping
            
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timeunit}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            params = {
                'apiKey': self.api_key,
                'adjusted': 'true',
                'sort': 'asc',
                'limit': 50000
            }
            
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