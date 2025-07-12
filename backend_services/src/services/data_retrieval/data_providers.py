# backend/src/services/data_providers.py
from abc import ABC, abstractmethod
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any
import yfinance as yf
import aiohttp
import asyncio

class BaseDataProvider(ABC):
    """Abstract base class for data providers"""
    
    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pd.DataFrame:
        """Get historical OHLCV data"""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote for a symbol"""
        pass

class YahooFinanceProvider(BaseDataProvider):
    """Yahoo Finance data provider"""
    
    def __init__(self):
        self.timeframe_map = {
            '1m': '1m',
            '2m': '2m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '60m': '60m',
            '1h': '60m',
            '1d': '1d',
            '1D': '1d',
            '5d': '5d',
            '1wk': '1wk',
            '1W': '1wk',
            '1mo': '1mo',
            '3mo': '3mo'
        }
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pd.DataFrame:
        """Get historical data from Yahoo Finance"""
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        
        def fetch_data():
            ticker = yf.Ticker(symbol)
            interval = self.timeframe_map.get(timeframe, '1d')
            
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
    
    def __init__(self, api_key: str, secret_key: str, base_url: str = 'https://data.alpaca.markets'):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.headers = {
            'APCA-API-KEY-ID': api_key,
            'APCA-API-SECRET-KEY': secret_key
        }
        
        self.timeframe_map = {
            '1m': '1Min',
            '5m': '5Min',
            '15m': '15Min',
            '30m': '30Min',
            '1h': '1Hour',
            '1d': '1Day',
            '1D': '1Day',
            '1w': '1Week',
            '1W': '1Week'
        }
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pd.DataFrame:
        """Get historical data from Alpaca"""
        async with aiohttp.ClientSession() as session:
            timeframe_str = self.timeframe_map.get(timeframe, '1Day')
            
            url = f"{self.base_url}/v2/stocks/{symbol}/bars"
            params = {
                'start': start_date.isoformat() + 'Z',
                'end': end_date.isoformat() + 'Z',
                'timeframe': timeframe_str,
                'limit': 10000,
                'page_token': None
            }
            
            all_bars = []
            
            while True:
                async with session.get(url, headers=self.headers, params=params) as response:
                    data = await response.json()
                    
                    if 'bars' in data:
                        all_bars.extend(data['bars'])
                    
                    # Check if there's more data
                    if 'next_page_token' in data and data['next_page_token']:
                        params['page_token'] = data['next_page_token']
                    else:
                        break
            
            # Convert to DataFrame
            if all_bars:
                df = pd.DataFrame(all_bars)
                df['t'] = pd.to_datetime(df['t'])
                df.set_index('t', inplace=True)
                
                # Rename columns
                df.rename(columns={
                    'o': 'open',
                    'h': 'high',
                    'l': 'low',
                    'c': 'close',
                    'v': 'volume'
                }, inplace=True)
                
                return df[['open', 'high', 'low', 'close', 'volume']]
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
                        'timestamp': pd.to_datetime(quote.get('t'))
                    }
                else:
                    return {}

class PolygonProvider(BaseDataProvider):
    """Polygon.io data provider"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = 'https://api.polygon.io'
        
        self.timeframe_map = {
            '1m': ('minute', 1),
            '5m': ('minute', 5),
            '15m': ('minute', 15),
            '30m': ('minute', 30),
            '1h': ('hour', 1),
            '1d': ('day', 1),
            '1D': ('day', 1),
            '1w': ('week', 1),
            '1W': ('week', 1)
        }
    
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str
    ) -> pd.DataFrame:
        """Get historical data from Polygon"""
        async with aiohttp.ClientSession() as session:
            timeunit, multiplier = self.timeframe_map.get(timeframe, ('day', 1))
            
            url = f"{self.base_url}/v2/aggs/ticker/{symbol}/range/{multiplier}/{timeunit}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
            params = {
                'apiKey': self.api_key,
                'adjusted': 'true',
                'sort': 'asc',
                'limit': 50000
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'results' in data and data['results']:
                    df = pd.DataFrame(data['results'])
                    
                    # Convert timestamp to datetime
                    df['t'] = pd.to_datetime(df['t'], unit='ms')
                    df.set_index('t', inplace=True)
                    
                    # Rename columns
                    df.rename(columns={
                        'o': 'open',
                        'h': 'high',
                        'l': 'low',
                        'c': 'close',
                        'v': 'volume'
                    }, inplace=True)
                    
                    return df[['open', 'high', 'low', 'close', 'volume']]
                else:
                    return pd.DataFrame()
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote from Polygon"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/v2/last/trade/{symbol}"
            params = {'apiKey': self.api_key}
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                
                if 'results' in data:
                    result = data['results']
                    return {
                        'symbol': symbol,
                        'price': result.get('p', 0),
                        'bid': 0,  # Polygon doesn't provide bid/ask in this endpoint
                        'ask': 0,
                        'volume': result.get('s', 0),
                        'timestamp': pd.to_datetime(result.get('t'), unit='ns')
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