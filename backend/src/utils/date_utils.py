import logging
from datetime import datetime, date, timedelta
from typing import Union

logger = logging.getLogger(__name__)

class DateUtils:
    """Utility functions for date handling"""
    
    @staticmethod
    def convert_to_datetime(date_input: Union[str, datetime, date]) -> datetime:
        """Convert various date formats to datetime object"""
        if isinstance(date_input, datetime):
            return date_input
        elif isinstance(date_input, date):
            return datetime.combine(date_input, datetime.min.time())
        elif isinstance(date_input, str):
            try:
                # Try parsing as ISO format first
                if 'T' in date_input or 'Z' in date_input:
                    # Handle ISO format with timezone
                    date_input = date_input.replace('Z', '+00:00')
                    return datetime.fromisoformat(date_input)
                else:
                    # Handle simple date format (YYYY-MM-DD)
                    return datetime.strptime(date_input, '%Y-%m-%d')
            except ValueError as e:
                logger.error(f"Error parsing date string '{date_input}': {e}")
                raise ValueError(f"Invalid date format: {date_input}. Expected YYYY-MM-DD or ISO format")
        else:
            raise ValueError(f"Unsupported date type: {type(date_input)}. Expected str, datetime, or date")
    
    @staticmethod
    def format_date_for_api(date_obj: Union[datetime, date]) -> str:
        """Format date for API requests"""
        if isinstance(date_obj, datetime):
            return date_obj.isoformat() + 'Z'
        elif isinstance(date_obj, date):
            return datetime.combine(date_obj, datetime.min.time()).isoformat() + 'Z'
        else:
            raise ValueError(f"Unsupported date type: {type(date_obj)}")
    
    @staticmethod
    def validate_date_range(start_date: Union[str, datetime, date], 
                          end_date: Union[str, datetime, date]) -> bool:
        """Validate that start_date is before end_date"""
        start_dt = DateUtils.convert_to_datetime(start_date)
        end_dt = DateUtils.convert_to_datetime(end_date)
        
        if start_dt >= end_dt:
            raise ValueError("Start date must be before end date")
        
        return True
    
    @staticmethod
    def get_trading_days(start_date: Union[str, datetime, date], 
                        end_date: Union[str, datetime, date]) -> int:
        """Get number of trading days between dates (approximate)"""
        start_dt = DateUtils.convert_to_datetime(start_date)
        end_dt = DateUtils.convert_to_datetime(end_date)
        
        # Simple calculation (doesn't account for holidays/weekends)
        delta = end_dt - start_dt
        return delta.days
    
    @staticmethod
    def is_market_hours(dt: datetime) -> bool:
        """Check if datetime is during market hours (9:30 AM - 4:00 PM ET)"""
        # Convert to Eastern Time (simplified)
        # In production, you'd use pytz for proper timezone handling
        hour = dt.hour
        minute = dt.minute
        
        # Market hours: 9:30 AM - 4:00 PM ET
        market_start = 9 * 60 + 30  # 9:30 AM in minutes
        market_end = 16 * 60  # 4:00 PM in minutes
        current_time = hour * 60 + minute
        
        return market_start <= current_time <= market_end
    
    @staticmethod
    def get_next_market_open(dt: datetime) -> datetime:
        """Get the next market open time"""
        # Simplified implementation
        # In production, you'd account for weekends and holidays
        if dt.weekday() >= 5:  # Saturday or Sunday
            # Move to next Monday
            days_ahead = 7 - dt.weekday()
            dt = dt + timedelta(days=days_ahead)
        
        # Set to 9:30 AM
        return dt.replace(hour=9, minute=30, second=0, microsecond=0) 