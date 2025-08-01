import asyncio
import logging
import polars as pl
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from .data_providers import DataProviderFactory, BaseDataProvider, TIMEFRAME_MAPPINGS
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
                        logger.info(f"DEBUG DATA MANAGER: Decrypted Alpaca secret key: {decrypted_secret}")
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
                        logger.info(f"DEBUG DATA MANAGER: Decrypted Polygon API key: {decrypted_api_key}")
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
    
    async def fetch_historical_data(self, symbols: List[str], start_date: str, end_date: str, timeframe: str, data_provider: str) -> pl.DataFrame:
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
                        timeframe=timeframe,
                        data_provider=data_provider
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
    
    async def fetch_data(self, symbols: List[str], timeframe: str, limit: int, data_provider: str) -> pl.DataFrame:
        """
        Fetches the latest market data for a set of symbols, up to a specified limit.

        This function calculates a suitable start date to ensure enough data is retrieved
        to satisfy the limit, accounting for non-trading days.
        """
        logger.info(f"Fetching latest {limit} data points for {symbols} with timeframe {timeframe} using {data_provider}")

        end_date = datetime.now()
        
        # Get the timeframe category and calculate lookback period
        days_to_look_back = self._calculate_lookback_days(timeframe, limit)

        start_date = end_date - timedelta(days=max(1, days_to_look_back))
        
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        symbols = [symbol.upper() for symbol in symbols]

        try:
            historical_data = await self.fetch_historical_data(
                symbols=symbols,
                start_date=start_date_str,
                end_date=end_date_str,
                timeframe=timeframe,
                data_provider=data_provider
            )

            if historical_data.height == 0:
                return historical_data

            # Ensure we only return the last `limit` data points per symbol
            return historical_data.group_by('symbol', maintain_order=True).tail(limit)

        except Exception as e:
            logger.error(f"Failed to fetch latest market data: {e}")
            # Return an empty DataFrame on failure to prevent crashes downstream
            return pl.DataFrame()

    def _calculate_lookback_days(self, timeframe: str, limit: int) -> int:
        """
        Calculate the number of days to look back based on timeframe and limit.
        Uses the TIMEFRAME_MAPPINGS to categorize timeframes properly.
        """
        from .data_providers import TIMEFRAME_MAPPINGS
        
        # Normalize timeframe to match our mappings
        normalized_timeframe = self._normalize_timeframe(timeframe)
        
        if normalized_timeframe not in TIMEFRAME_MAPPINGS:
            logger.warning(f"Unknown timeframe format: {timeframe}. Using daily assumption for lookback calculation.")
            return int(limit * 1.8)  # Default assumption: ~7 trading days in 10 calendar days
        
        # Determine timeframe category based on the normalized timeframe
        if normalized_timeframe in ['1M', '2M', '5M', '15M', '30M']:
            # Minute-based timeframes
            minutes = self._extract_minutes_from_timeframe(normalized_timeframe)
            # Assume 6.5 trading hours per day (390 minutes)
            trading_days_needed = (limit * minutes) / 390
            # Add buffer for weekends, holidays, and market closures
            return int(trading_days_needed * 2.5) + 5
            
        elif normalized_timeframe in ['60M', '1H']:
            # Hour-based timeframes
            hours = 1  # Both 60M and 1H represent 1 hour
            # Assume 6.5 trading hours per day
            trading_days_needed = (limit * hours) / 6.5
            return int(trading_days_needed * 2.5) + 5
            
        elif normalized_timeframe in ['1d', '1D']:
            # Daily timeframes
            return int(limit * 1.8)  # ~7 trading days in 10 calendar days
            
        elif normalized_timeframe in ['1wk', '1w', '1W']:
            # Weekly timeframes
            return limit * 10  # Assume ~10 calendar days per trading week
            
        elif normalized_timeframe in ['1mo', '3mo']:
            # Monthly timeframes
            return limit * 35  # Assume ~35 days per month
            
        else:
            # Fallback for any other timeframes
            logger.warning(f"Unhandled timeframe category for: {timeframe}. Using daily assumption.")
            return int(limit * 1.8)

    def _normalize_timeframe(self, timeframe: str) -> str:
        """
        Normalize various timeframe formats to match TIMEFRAME_MAPPINGS keys.
        """
        # Handle common variations
        timeframe_upper = timeframe.upper()
        
        # Map common variations to our standard format
        variations = {
            '1MIN': '1M',
            '5MIN': '5M', 
            '15MIN': '15M',
            '30MIN': '30M',
            '60MIN': '60M',
            '1HOUR': '1H',
            '1DAY': '1D',
            '1WEEK': '1W',
            '1MONTH': '1mo',
            # Add more variations as needed
        }
        
        if timeframe_upper in variations:
            return variations[timeframe_upper]
        
        # If it's already in our mapping, return as-is
        if timeframe in TIMEFRAME_MAPPINGS or timeframe_upper in TIMEFRAME_MAPPINGS:
            return timeframe if timeframe in TIMEFRAME_MAPPINGS else timeframe_upper
        
        # Try lowercase version
        timeframe_lower = timeframe.lower()
        if timeframe_lower in TIMEFRAME_MAPPINGS:
            return timeframe_lower
            
        return timeframe  # Return original if no mapping found

    def _extract_minutes_from_timeframe(self, timeframe: str) -> int:
        """Extract the number of minutes from minute-based timeframes."""
        minute_mappings = {
            '1M': 1,
            '2M': 2,
            '5M': 5,
            '15M': 15,
            '30M': 30,
            '60M': 60
        }
        return minute_mappings.get(timeframe, 1)

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