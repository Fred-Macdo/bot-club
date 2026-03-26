import logging
import operator
from typing import Dict, Any, List, Union, Tuple, Optional

logger = logging.getLogger(__name__)

class ConditionChecker:
    """Handles entry and exit condition checking"""
    
    def check_entry_conditions(self, conditions: List[Dict], row: Dict[str, Any]) -> Tuple[bool, Optional[Dict]]:
        """
        Check if ALL entry conditions are met.
        Returns (True, row) if all pass, (False, None) otherwise.
        """
        if not conditions:
            return False, None
        
        for condition in conditions:
            if not self._check_condition(row, condition):
                return False, None
        
        return True, row

    def check_exit_conditions(self, conditions: List[Dict], row: Dict[str, Any]) -> Tuple[bool, Optional[List[bool]], Optional[Dict]]:
        """
        Check if ANY exit condition is met.
        Returns (True, conditions_met_list, row) if any pass, (False, None, None) otherwise.
        """
        if not conditions:
            return False, None, None
        
        conditions_met = []
        any_met = False
        
        for condition in conditions:
            met = self._check_condition(row, condition)
            conditions_met.append(met)
            if met:
                any_met = True
        
        if any_met:
            return True, conditions_met, row
        
        return False, None, None
    
    def _check_condition(self, row: Dict[str, Any], condition_config: Dict) -> bool:
        """Route to the appropriate comparison handler"""
        comparison = condition_config.get('comparison', condition_config.get('operator', ''))
        indicator_key = condition_config.get('indicator', '').lower()
        value = condition_config.get('value')
        
        if not indicator_key or not comparison or value is None:
            logger.debug(f"Invalid condition: {condition_config}")
            return False
        
        comparison = comparison.lower()
        
        if comparison == 'crosses_above':
            return self._check_crosses_above(row, indicator_key, value)
        elif comparison == 'crosses_below':
            return self._check_crosses_below(row, indicator_key, value)
        elif comparison in ('above', '>'):
            return self._check_above(row, indicator_key, value)
        elif comparison in ('below', '<'):
            return self._check_below(row, indicator_key, value)
        elif comparison in ('>=', 'above_or_equal'):
            return self._check_above_or_equal(row, indicator_key, value)
        elif comparison in ('<=', 'below_or_equal'):
            return self._check_below_or_equal(row, indicator_key, value)
        elif comparison in ('==', 'equals'):
            return self._check_equals(row, indicator_key, value)
        else:
            logger.warning(f"Unknown comparison type: {comparison}")
            return False
    
    def _resolve_current_and_prev(self, row: Dict[str, Any], value: Union[str, int, float]) -> Tuple[Optional[float], Optional[float]]:
        """
        Resolve the current and previous value for the 'value' side of a condition.
        
        If value is a column name (string found in row), return (row[value], row[value_prev]).
        If value is a numeric constant, return (number, number) — constants don't change bar to bar.
        """
        if isinstance(value, str):
            value_lower = value.lower()
            # Check if it's a column name
            if value_lower in row:
                current = row.get(value_lower)
                prev = row.get(f'{value_lower}_prev')
                try:
                    return float(current) if current is not None else None, float(prev) if prev is not None else None
                except (ValueError, TypeError):
                    return None, None
            # Otherwise try parsing as number
            try:
                num = float(value)
                return num, num  # Constant: same for current and prev
            except (ValueError, TypeError):
                return None, None
        else:
            try:
                num = float(value)
                return num, num  # Constant: same for current and prev
            except (ValueError, TypeError):
                return None, None

    def _check_crosses_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Crossover above: indicator was <= value on prev bar, now > value on current bar.
        """
        current_ind = row.get(indicator_key)
        prev_ind = row.get(f'{indicator_key}_prev')
        
        if current_ind is None or prev_ind is None:
            return False
        
        current_target, prev_target = self._resolve_current_and_prev(row, value)
        if current_target is None or prev_target is None:
            return False
        
        try:
            return float(prev_ind) <= prev_target and float(current_ind) > current_target
        except (ValueError, TypeError):
            return False

    def _check_crosses_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        """
        Crossover below: indicator was >= value on prev bar, now < value on current bar.
        """
        current_ind = row.get(indicator_key)
        prev_ind = row.get(f'{indicator_key}_prev')
        
        if current_ind is None or prev_ind is None:
            return False
        
        current_target, prev_target = self._resolve_current_and_prev(row, value)
        if current_target is None or prev_target is None:
            return False
        
        try:
            return float(prev_ind) >= prev_target and float(current_ind) < current_target
        except (ValueError, TypeError):
            return False

    def _check_above(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        current_ind = row.get(indicator_key)
        if current_ind is None:
            return False
        current_target, _ = self._resolve_current_and_prev(row, value)
        if current_target is None:
            return False
        try:
            return float(current_ind) > current_target
        except (ValueError, TypeError):
            return False

    def _check_below(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        current_ind = row.get(indicator_key)
        if current_ind is None:
            return False
        current_target, _ = self._resolve_current_and_prev(row, value)
        if current_target is None:
            return False
        try:
            return float(current_ind) < current_target
        except (ValueError, TypeError):
            return False

    def _check_above_or_equal(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        current_ind = row.get(indicator_key)
        if current_ind is None:
            return False
        current_target, _ = self._resolve_current_and_prev(row, value)
        if current_target is None:
            return False
        try:
            return float(current_ind) >= current_target
        except (ValueError, TypeError):
            return False

    def _check_below_or_equal(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        current_ind = row.get(indicator_key)
        if current_ind is None:
            return False
        current_target, _ = self._resolve_current_and_prev(row, value)
        if current_target is None:
            return False
        try:
            return float(current_ind) <= current_target
        except (ValueError, TypeError):
            return False

    def _check_equals(self, row: Dict[str, Any], indicator_key: str, value: Union[str, int, float]) -> bool:
        current_ind = row.get(indicator_key)
        if current_ind is None:
            return False
        current_target, _ = self._resolve_current_and_prev(row, value)
        if current_target is None:
            return False
        try:
            return float(current_ind) == current_target
        except (ValueError, TypeError):
            return False