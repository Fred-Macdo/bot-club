import asyncio
import logging
import polars as pl
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from .data_providers import DataProviderFactory, BaseDataProvider
from ..utils.date_utils import DateUtils

logger = logging.getLogger(__name__)

class DataManager:
    """Handles all data fetching and caching using DataProviderFactory"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.data_cache = {}
        self.data_provider = None
    
    async def initialize_provider(self, data_provider_name: str, user_id: str):
        """Initialize data provider using DataProviderFactory"""
        try:
            # Get user configuration for API keys only
            user_config = await self.db['user_config'].find_one({"user_id": user_id})
            
            if data_provider_name.lower() == 'yahoo':
                self.data_provider = DataProviderFactory.get_provider('yahoo')
                logger.info("Initialized Yahoo Finance data provider")
                
            elif data_provider_name.lower() == 'alpaca':
                if not user_config:
                    logger.warning(f"No user configuration found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    return
                
                # Get API keys from user config
                api_key = user_config.get('alpaca_paper_api_key') or user_config.get('alpaca_live_api_key')
                secret_key = user_config.get('alpaca_paper_secret_key') or user_config.get('alpaca_live_secret_key')
                
                if api_key and secret_key:
                    # Decrypt secret key if needed
                    try:
                        from models.user_config import ConfigEncryption
                        decrypted_secret = ConfigEncryption.decrypt_value(secret_key)
                    except Exception as e:
                        logger.warning(f"Could not decrypt secret key, using as-is: {e}")
                        decrypted_secret = secret_key
                    
                    self.data_provider = DataProviderFactory.get_provider(
                        'alpaca',
                        api_key=api_key,
                        secret_key=decrypted_secret
                    )
                    logger.info("Initialized Alpaca data provider")
                else:
                    logger.warning(f"Alpaca API keys not found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    
            elif data_provider_name.lower() == 'polygon':
                if not user_config:
                    logger.warning(f"No user configuration found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    return
                
                # Get the actual API key (polygon_secret_key), not the key name
                api_key = user_config.get('polygon_secret_key')
                
                if api_key:
                    # Decrypt the API key if needed
                    try:
                        from models.user_config import ConfigEncryption
                        decrypted_api_key = ConfigEncryption.decrypt_value(api_key)
                    except Exception as e:
                        logger.warning(f"Could not decrypt Polygon API key, using as-is: {e}")
                        decrypted_api_key = api_key
                    
                    self.data_provider = DataProviderFactory.get_provider('polygon', api_key=decrypted_api_key)
                    logger.info("Initialized Polygon data provider")
                else:
                    logger.warning(f"Polygon API key not found for user {user_id}, falling back to Yahoo Finance")
                    self.data_provider = DataProviderFactory.get_provider('yahoo')
                    
            else:
                logger.warning(f"Unknown data provider '{data_provider_name}', falling back to Yahoo Finance")
                self.data_provider = DataProviderFactory.get_provider('yahoo')
                
        except Exception as e:
            logger.error(f"Error initializing data provider: {e}, falling back to Yahoo Finance")
            self.data_provider = DataProviderFactory.get_provider('yahoo')
    
    async def fetch_historical_data(self, symbols: List[str], start_date: str, end_date: str, timeframe: str) -> pl.DataFrame:
        """Fetch historical data for symbols using the initialized provider"""
        cache_key = f"{'-'.join(symbols)}_{start_date}_{end_date}_{timeframe}_{self.data_provider.get_provider_name()}"
        
        if cache_key in self.data_cache:
            logger.info(f"Using cached data for {symbols}")
            return self.data_cache[cache_key]
        
        logger.info(f"Fetching data for {symbols} from {start_date} to {end_date} using {self.data_provider.get_provider_name()}")
        
        try:
            start_dt = self._convert_to_datetime(start_date)
            end_dt = self._convert_to_datetime(end_date)
            
            all_data = []
            for symbol in symbols:
                try:
                    data = await self.data_provider.get_historical_data(
                        symbol=symbol,
                        start_date=start_dt,
                        end_date=end_dt,
                        timeframe=timeframe
                    )
                    
                    # Fix: Check if Polars DataFrame is empty using height
                    if data.height > 0:  # Polars uses .height instead of .empty
                        # Add symbol column if it doesn't exist
                        if 'symbol' not in data.columns:
                            data = data.with_columns(pl.lit(symbol).alias("symbol"))
                        all_data.append(data)
                        logger.info(f"Retrieved {data.height} data points for {symbol}")
                    else:
                        logger.warning(f"No data retrieved for {symbol}")
                        
                except Exception as e:
                    logger.error(f"Error fetching data for {symbol}: {e}")
                    continue
            
            if not all_data:
                raise ValueError("No data retrieved for any symbols")
            
            combined_data = pl.concat(all_data, how="vertical")
            combined_data = self._standardize_columns(combined_data)
            combined_data = combined_data.sort(["datetime", "symbol"])
            
            self.data_cache[cache_key] = combined_data
            logger.info(f"Retrieved {len(combined_data)} total data points")
            return combined_data
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            raise
    
    def _convert_to_datetime(self, date_input) -> datetime:
        """Convert various date formats to datetime"""
        if isinstance(date_input, datetime):
            return date_input
        elif isinstance(date_input, date):  # Add support for date objects
            return datetime.combine(date_input, datetime.min.time())
        elif isinstance(date_input, str):
            # Try different date formats
            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
                try:
                    return datetime.strptime(date_input, fmt)
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse date string: {date_input}")
        else:
            raise ValueError(f"Unsupported date type: {type(date_input)}")
    
    def _standardize_columns(self, df: pl.DataFrame) -> pl.DataFrame:
        """Standardize column names across different providers"""
        column_mapping = {
            'Date': 'datetime', 'Datetime': 'datetime', 
            'date': 'datetime', 'time': 'datetime', 
            'timestamp': 'datetime', 't': 'datetime',
            'Open': 'open', 'o': 'open', 'open': 'open', 'high': 'high', 
            'High': 'high', 'h': 'high', 'Low': 'low', 'l': 'low', 'low': 'low', 
            'Close': 'close', 'c': 'close', 'close': 'close', 
             'volume': 'volume', 'Volume': 'volume', 'v': 'volume',
        }
        
        existing_cols = df.columns
        rename_dict = {col: column_mapping[col] for col in existing_cols if col in column_mapping}
        if rename_dict:
            df = df.rename(rename_dict)
        
        required_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume', 'symbol']
        for col in required_columns:
            if col not in df.columns:
                if col == 'datetime':
                    df = df.with_columns(pl.arange(0, len(df)).alias('datetime'))
                else:
                    df = df.with_columns(pl.lit(0).alias(col))
        
        return df
    
    def get_supported_timeframes(self) -> List[str]:
        """Get supported timeframes for the current data provider"""
        if self.data_provider is None:
            return []
        provider_name = self.data_provider.get_provider_name()
        supported = DataProviderFactory.get_supported_timeframes(provider_name)
        return supported.get(provider_name, [])
    
    def validate_timeframe(self, timeframe: str) -> bool:
        """Validate if a timeframe is supported by the current data provider"""
        if self.data_provider is None:
            return False
        supported_timeframes = self.get_supported_timeframes()
        return timeframe in supported_timeframes 