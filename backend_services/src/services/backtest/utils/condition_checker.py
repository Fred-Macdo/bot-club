import logging
from typing import Dict, Any, List, Union
from datetime import datetime

logger = logging.getLogger(__name__)

class ConditionChecker:
    """Handles entry and exit condition checking"""
    
    def check_entry_conditions(self, conditions: List[Dict], row: Dict[str, Any], symbol: str) -> bool:
        """Check if entry conditions are met"""
        if not conditions:
            return False
        
        return all(
            self._check_condition(row, condition)
            for condition in conditions
        )
    
    def check_exit_conditions(self, conditions: List[Dict], row: Dict[str, Any], symbol: str, position: 'Position', current_time: datetime) -> bool:
        """Check if exit conditions are met"""
        if not conditions:
            # Default exit conditions
            current_price = row.get('close', position.entry_price)
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            
            # Exit after 10% profit/loss or 5 days
            if abs(pnl_pct) > 0.1 or position.get_days_held(current_time) > 5:
                return True
            return False
        
        return any(
            self._check_condition(row, condition)
            for condition in conditions
        )
    
    def _check_condition(self, row: Dict[str, Any], condition_config: Dict) -> bool:
        """Check entry/exit condition"""
        valid_comparisons = ['above', 'below', 'between', 'crosses_above', 'crosses_below', 'equals']
        comparison = condition_config.get('comparison')
        
        if comparison not in valid_comparisons:
            raise ValueError(f"Comparison '{comparison}' is not valid. Must be one of {valid_comparisons}")
        
        indicator = condition_config.get('indicator')
        value = condition_config.get('value')
        
        # Ensure indicator is lowercase for consistent access
        indicator_key = indicator.lower()
        
        # Handle special indicators with dedicated comparisons
        if indicator == "MACD" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_macd_cross(row, comparison)
        
        elif indicator == "BBANDS" and comparison in ["crosses_above", "crosses_below"]:
            return self._check_bbands_cross(row, comparison, value)
        
        # Handle general comparison cases
        if comparison == "above":
            return self._check_above(row, indicator_key, value)
        
        elif comparison == "below":
            return self._check_below(row, indicator_key, value)
        
        elif comparison == "crosses_above":
            return self._check_crosses_above(row, indicator_key, value)
        
        elif comparison == "crosses_below":
            return self._check_crosses_below(row, indicator_key, value)
        
        elif comparison == "between":
            return self._check_between(row, indicator_key, value)
        
        elif comparison == "equals":
            if isinstance(value, str):
                return row[indicator_key] == row[value.lower()]
            else:
                return row[indicator_key] == value
        
        return False
    
    def _check_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator is above a value or another indicator"""
        if indicator_key not in row:
            return False
        
        indicator_value = row[indicator_key]
        if indicator_value is None:
            return False
        
        try:
            indicator_value = float(indicator_value)
        except (ValueError, TypeError):
            return False
        
        try:
            comparison_value = float(value)
            return indicator_value > comparison_value
        except (ValueError, TypeError):
            value_key = str(value).lower()
            if value_key not in row:
                return False
            
            try:
                comparison_value = float(row[value_key])
                return indicator_value > comparison_value
            except (ValueError, TypeError):
                return False
    
    def _check_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator is below a value or another indicator"""
        if indicator_key not in row:
            return False
        
        indicator_value = row[indicator_key]
        if indicator_value is None:
            return False
        
        try:
            indicator_value = float(indicator_value)
        except (ValueError, TypeError):
            return False
        
        try:
            comparison_value = float(value)
            return indicator_value < comparison_value
        except (ValueError, TypeError):
            value_key = str(value).lower()
            if value_key not in row:
                return False
            
            try:
                comparison_value = float(row[value_key])
                return indicator_value < comparison_value
            except (ValueError, TypeError):
                return False
    
    def _check_crosses_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator crosses above a value or another indicator"""
        if indicator_key not in row or f"{indicator_key}_prev" not in row:
            return False
        
        try:
            indicator_value = float(value)
            return (indicator_value > row[indicator_key]) and (row[f"{indicator_key}_prev"] <= indicator_value)
        except (ValueError, TypeError):
            if isinstance(value, str):
                value_key = value.lower()
                if f"{value_key}_prev" not in row:
                    return False
                return (row[indicator_key] > row[value_key]) and (row[f"{indicator_key}_prev"] <= row[f"{value_key}_prev"])
    
    def _check_crosses_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """Check if indicator crosses below a value or another indicator"""
        if indicator_key not in row or f"{indicator_key}_prev" not in row:
            return False
        
        try:
            indicator_value = float(value)
            return (indicator_value < row[indicator_key]) and (row[f"{indicator_key}_prev"] >= indicator_value)
        except (ValueError, TypeError):
            if isinstance(value, str):
                value_key = value.lower()
                if f"{value_key}_prev" not in row:
                    return False
                return (row[indicator_key] < row[value_key]) and (row[f"{indicator_key}_prev"] >= row[f"{value_key}_prev"])
    
    def _check_between(self, row: Dict[str, Any], indicator_key: str, value: List[Union[str, int, float]]) -> bool:
        """Check if indicator value is between two bounds"""
        if indicator_key not in row:
            return False
        
        try:
            if all(isinstance(x, (int, float)) for x in value):
                return value[0] <= row[indicator_key] <= value[1]
            else:
                lower_value = row[value[0].lower()] if isinstance(value[0], str) else value[0]
                upper_value = row[value[1].lower()] if isinstance(value[1], str) else value[1]
                return lower_value <= row[indicator_key] <= upper_value
        except (KeyError, TypeError):
            return False
    
    def _check_macd_cross(self, row: Dict[str, Any], comparison: str) -> bool:
        """Handle MACD specific crossing logic"""
        required_keys = ['macd', 'macd_signal', 'macd_prev', 'macdsignal_prev']
        if not all(key in row for key in required_keys):
            return False
        
        if comparison == "crosses_above":
            return (row['macd'] > row['macd_signal']) and (row['macd_prev'] <= row['macdsignal_prev'])
        else:  # crosses_below
            return (row['macd'] < row['macd_signal']) and (row['macd_prev'] >= row['macdsignal_prev'])
    
    def _check_bbands_cross(self, row: Dict[str, Any], comparison: str, value: str) -> bool:
        """Handle Bollinger Bands specific crossing logic"""
        value_key = value.lower() if isinstance(value, str) else value
        required_keys = ['close', 'close_prev', value_key]
        if not all(key in row for key in required_keys):
            return False
        
        if comparison == "crosses_above":
            return (row['close'] > row[value_key]) and (row['close_prev'] <= row[value_key])
        else:  # crosses_below
            return (row['close'] < row[value_key]) and (row['close_prev'] >= row[value_key]) 