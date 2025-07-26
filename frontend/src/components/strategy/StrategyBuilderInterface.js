import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Typography,
  Grid,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Chip,
  IconButton,
  Card,
  List,
  ListItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar,
  Alert,
  Autocomplete,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Container,
  Paper
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Save as SaveIcon,
  PlayArrow as PlayArrowIcon,
  Code as CodeIcon,
  TrendingUp as IndicatorIcon,
  ExpandMore as ExpandMoreIcon,
  Info as InfoIcon,
  Assessment as AssessmentIcon,
  Settings as SettingsIcon,
  AccountBalance as AccountBalanceIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon
} from '@mui/icons-material';
import { saveStrategy } from '../../api/Client';
import { useAuth } from '../router/AuthContext';

const StrategyBuilderInterface = () => {
  const { user } = useAuth();
    // Strategy Configuration State
  const [strategyName, setStrategyName] = useState('New Strategy');
  const [strategyDescription, setStrategyDescription] = useState('');
  const [symbolInput, setSymbolInput] = useState(''); // For adding new symbols
  const [strategyConfig, setStrategyConfig] = useState({
    symbols: ["AAPL", "MSFT", "GOOG"],
    timeframe: "1d",
    start_date: "2024-01-01",
    end_date: "2024-12-31",
    entry_conditions: [
      {
        indicator: "ema_5",
        comparison: "crosses_above",
        value: "sma_20"
      }
    ],
    exit_conditions: [
      {
        indicator: "rsi",
        comparison: "crosses_above",
        value: "70"
      }
    ],
    risk_management: {
      position_sizing_method: "risk_based",
      risk_per_trade: 0.02,
      stop_loss: 0.05,
      take_profit: 0.10,
      max_position_size: 10000.0,
      atr_multiplier: 2.0
    },
    // Add DCA configuration
    dollar_cost_averaging: {
      enabled: false,
      max_positions: 3
    },
    indicators: [
      {
        name: "SMA",
        params: {
          period: 20
        }
      },
      {
        name: "EMA",
        params: {
          period: 5
        }
      },
      {
        name: "RSI",
        params: {
          period: 14
        }
      }
    ]
  });
  // UI State
  const [isCodeViewOpen, setIsCodeViewOpen] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [yamlConfig, setYamlConfig] = useState('');
  
  // Accordion state
  const [expanded, setExpanded] = useState({
    basicInfo: true,
    instruments: false,
    indicators: false,
    entryConditions: false,
    exitConditions: false,
    riskManagement: false
  });
  // Available options
  const availableIndicators = [
    { name: 'SMA', label: 'Simple Moving Average', defaultParams: { period: 20 } },
    { name: 'EMA', label: 'Exponential Moving Average', defaultParams: { period: 12 } },
    { name: 'RSI', label: 'Relative Strength Index', defaultParams: { period: 14 } },
    { name: 'MACD', label: 'MACD', defaultParams: { fast: 12, slow: 26, signal: 9 } },
    { name: 'Bollinger_Bands', label: 'Bollinger Bands', defaultParams: { period: 20, std: 2 } },
    { name: 'ATR', label: 'Average True Range', defaultParams: { period: 14 } },
    { name: 'Stochastic', label: 'Stochastic Oscillator', defaultParams: { k_period: 14, d_period: 3 } },
    { name: 'CCI', label: 'Commodity Channel Index', defaultParams: { period: 14 } },
    { name: 'VWAP', label: 'Volume Weighted Average Price', defaultParams: { period: 20 } },
    { name: 'MFI', label: 'Money Flow Index', defaultParams: { period: 14 } },
    { name: 'ADX', label: 'Average Directional Index', defaultParams: { period: 14 } },
    { name: 'OBV', label: 'On Balance Volume', defaultParams: { period: 14 } }
  ];  const comparisons = ['crosses_above', 'crosses_below', 'greater_than', 'less_than', 'equals', 'between'];
  const timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w'];
    // Popular symbols for autocomplete suggestions
  const popularSymbols = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'AMD', 'CRM', 'BTC-USD', 'ETH-USD', 'SPY', 'QQQ', 'VOO'];
  // Available value options for conditions
  const ohlcvColumns = ['Open', 'High', 'Low', 'Close', 'Volume'];
  
  // Get available indicator values based on current indicators
  const getAvailableIndicatorValues = () => {
    const indicatorValues = [];
    
    strategyConfig.indicators.forEach(indicator => {
      const period = indicator.params.period || Object.values(indicator.params)[0];
      const baseName = indicator.name.toLowerCase();
      
      // Handle complex indicators with multiple outputs
      switch (baseName) {
        case 'macd':
          indicatorValues.push(
            `macd_line`,
            `macd_signal`,
            `macd_hist`
          );
          break;
          
        case 'bollinger_bands':
          indicatorValues.push(
            `upperband`,
            `middleband`,
            `lowerband`
          );
          break;
          
        case 'stochastic':
          const kPeriod = indicator.params.k_period || 14;
          const dPeriod = indicator.params.d_period || 3;
          indicatorValues.push(
            `stoch_k_${kPeriod}`,
            `stoch_d_${dPeriod}`
          );
          break;
          
        case 'adx':
          indicatorValues.push(
            `adx_${period}`,
            `di_plus_${period}`,
            `di_minus_${period}`
          );
          break;
          
        default:
          // Simple indicators with single output
          indicatorValues.push(`${baseName}_${period}`);
          break;
      }
    });
    
    return indicatorValues;
  };
  
  // Get available value options for conditions
  const getAvailableValueOptions = () => {
    const indicatorValues = getAvailableIndicatorValues();
    return [...ohlcvColumns, ...indicatorValues];
  };
  // Smart value input component
  const ValueInput = ({ value, onChange, label = "Value" }) => {
    const availableOptions = getAvailableValueOptions();
    
    return (
      <Autocomplete
        freeSolo
        fullWidth
        size="small"
        options={availableOptions}
        value={value}
        onInputChange={(event, newValue) => {
          onChange(newValue || '');
        }}
        renderInput={(params) => (
          <TextField
            {...params}
            label={label}
            placeholder="Select or type value"
          />
        )}
      />
    );
  };  // Range value input component for "between" conditions
  const RangeValueInput = ({ lowValue, highValue, onLowChange, onHighChange }) => {
    const availableOptions = getAvailableValueOptions();
    
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
          <Typography variant="caption" color="text.secondary">
            Between Range:
          </Typography>
        </Box>
        <Autocomplete
          freeSolo
          fullWidth
          size="small"
          options={availableOptions}
          value={lowValue}
          onInputChange={(event, newValue) => {
            onLowChange(newValue || '');
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              label="Low"
              placeholder="Low value"
              size="small"
            />
          )}
        />
        <Autocomplete
          freeSolo
          fullWidth
          size="small"
          options={availableOptions}
          value={highValue}
          onInputChange={(event, newValue) => {
            onHighChange(newValue || '');
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              label="High"
              placeholder="High value"
              size="small"
            />
          )}
        />
      </Box>
    );
  };// Generate YAML configuration
  const generateYamlConfig = useCallback(() => {
    const formatCondition = (condition) => {
      if (condition.comparison === 'between') {
        return `    - indicator: "${condition.indicator}"
      comparison: "${condition.comparison}"
      low_value: "${condition.low_value || ''}"
      high_value: "${condition.high_value || ''}"`;
      } else {
        return `    - indicator: "${condition.indicator}"
      comparison: "${condition.comparison}"
      value: "${condition.value}"`;
      }
    };

    const yaml = `name: "${strategyName}"
description: "${strategyDescription}"
config:
  symbols: [${strategyConfig.symbols.map(s => `"${s}"`).join(', ')}]
  timeframe: "${strategyConfig.timeframe}"
  start_date: "${strategyConfig.start_date}"
  end_date: "${strategyConfig.end_date}"
  
  entry_conditions:
${strategyConfig.entry_conditions.map(formatCondition).join('\n')}

  exit_conditions:
${strategyConfig.exit_conditions.map(formatCondition).join('\n')}

  risk_management:
    position_sizing_method: "${strategyConfig.risk_management.position_sizing_method}"
    risk_per_trade: ${strategyConfig.risk_management.risk_per_trade}
    stop_loss: ${strategyConfig.risk_management.stop_loss}
    take_profit: ${strategyConfig.risk_management.take_profit}
    max_position_size: ${strategyConfig.risk_management.max_position_size}
    atr_multiplier: ${strategyConfig.risk_management.atr_multiplier}

  dollar_cost_averaging:
    enabled: ${strategyConfig.dollar_cost_averaging.enabled}
    max_positions: ${strategyConfig.dollar_cost_averaging.max_positions}

  indicators:
${strategyConfig.indicators.map(indicator => 
  `    - name: "${indicator.name}"
      params:
        period: ${indicator.params.period}`
).join('\n')}`;
    return yaml;
  }, [strategyName, strategyDescription, strategyConfig]);  // Handle condition updates
  const updateEntryCondition = (index, field, value) => {
    const newConditions = [...strategyConfig.entry_conditions];
    const condition = { ...newConditions[index] };
    
    // If changing comparison type, clean up values appropriately
    if (field === 'comparison') {
      if (value === 'between') {
        // Convert single value to range values
        condition.low_value = condition.value || '';
        condition.high_value = '';
        delete condition.value;
      } else if (condition.comparison === 'between') {
        // Convert range values to single value
        condition.value = condition.low_value || '';
        delete condition.low_value;
        delete condition.high_value;
      }
    }
    
    condition[field] = value;
    newConditions[index] = condition;
    setStrategyConfig({ ...strategyConfig, entry_conditions: newConditions });
  };

  const updateExitCondition = (index, field, value) => {
    const newConditions = [...strategyConfig.exit_conditions];
    const condition = { ...newConditions[index] };
    
    // If changing comparison type, clean up values appropriately
    if (field === 'comparison') {
      if (value === 'between') {
        // Convert single value to range values
        condition.low_value = condition.value || '';
        condition.high_value = '';
        delete condition.value;
      } else if (condition.comparison === 'between') {
        // Convert range values to single value
        condition.value = condition.low_value || '';
        delete condition.low_value;
        delete condition.high_value;
      }
    }
    
    condition[field] = value;
    newConditions[index] = condition;
    setStrategyConfig({ ...strategyConfig, exit_conditions: newConditions });
  };

  const addEntryCondition = () => {
    setStrategyConfig({
      ...strategyConfig,
      entry_conditions: [
        ...strategyConfig.entry_conditions,
        { indicator: 'sma_20', comparison: 'crosses_above', value: 'sma_50' }
      ]
    });
  };

  const addExitCondition = () => {
    setStrategyConfig({
      ...strategyConfig,
      exit_conditions: [
        ...strategyConfig.exit_conditions,
        { indicator: 'rsi', comparison: 'greater_than', value: '70' }
      ]
    });
  };

  const removeEntryCondition = (index) => {
    const newConditions = strategyConfig.entry_conditions.filter((_, i) => i !== index);
    setStrategyConfig({ ...strategyConfig, entry_conditions: newConditions });
  };

  const removeExitCondition = (index) => {
    const newConditions = strategyConfig.exit_conditions.filter((_, i) => i !== index);
    setStrategyConfig({ ...strategyConfig, exit_conditions: newConditions });
  };
  // Handle indicator management
  const addIndicator = (indicatorName) => {
    const indicator = availableIndicators.find(ind => ind.name === indicatorName);
    if (indicator) {
      setStrategyConfig({
        ...strategyConfig,
        indicators: [
          ...strategyConfig.indicators,
          {
            name: indicator.name,
            params: { ...indicator.defaultParams }
          }
        ]
      });
    }
  };

  const removeIndicator = (index) => {
    const newIndicators = strategyConfig.indicators.filter((_, i) => i !== index);
    setStrategyConfig({ ...strategyConfig, indicators: newIndicators });
  };

  const updateIndicatorParams = (index, paramName, value) => {
    const newIndicators = [...strategyConfig.indicators];
    newIndicators[index] = {
      ...newIndicators[index],
      params: {
        ...newIndicators[index].params,
        [paramName]: value
      }
    };
    setStrategyConfig({ ...strategyConfig, indicators: newIndicators });
  };

  // Handle symbol management
  const addSymbol = () => {
    if (symbolInput.trim() && !strategyConfig.symbols.includes(symbolInput.toUpperCase())) {
      setStrategyConfig({
        ...strategyConfig,
        symbols: [...strategyConfig.symbols, symbolInput.toUpperCase()]
      });
      setSymbolInput('');
    }
  };
  const removeSymbol = (index) => {
    const newSymbols = strategyConfig.symbols.filter((_, i) => i !== index);
    setStrategyConfig({ ...strategyConfig, symbols: newSymbols });
  };

  // Handle accordion changes
  const handleAccordionChange = (panel) => (event, isExpanded) => {
    setExpanded(prev => ({
      ...prev,
      [panel]: isExpanded
    }));
  };

  // Handle saving strategy
  const handleSaveStrategy = async () => {
    try {
      const result = await saveStrategy({
        name: strategyName,
        description: strategyDescription,
        config: strategyConfig
      }, user.id); // Swapped arguments

      if (result.success) {
        setSaveSuccess(true);
        setSaveError('');
      } else {
        setSaveError(result.error || 'Failed to save strategy');
      }
    } catch (error) {
      setSaveError('Error saving strategy: ' + error.message);
    }
  };  // Update YAML when config changes
  useEffect(() => {
    setYamlConfig(generateYamlConfig());
  }, [generateYamlConfig]);return (
    <Box>

      {/* Basic Information Accordion */}
      <Accordion 
        expanded={expanded.basicInfo} 
        onChange={handleAccordionChange('basicInfo')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <InfoIcon color="primary" />
            <Typography variant="h6">Basic Information</Typography>
            {strategyName !== 'New Strategy' && (
              <Chip label="Configured" color="success" size="small" />
            )}
          </Box>
        </AccordionSummary>        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Set the fundamental properties of your trading strategy
          </Typography>
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Strategy Name"
                value={strategyName}
                onChange={(e) => setStrategyName(e.target.value)}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={strategyConfig.timeframe}
                  onChange={(e) => setStrategyConfig({
                    ...strategyConfig,
                    timeframe: e.target.value
                  })}
                  label="Timeframe"
                >
                  {timeframes.map(tf => (
                    <MenuItem key={tf} value={tf}>{tf.toUpperCase()}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                value={strategyDescription}
                onChange={(e) => setStrategyDescription(e.target.value)}
                multiline
                rows={3}
                placeholder="Describe your strategy's approach and goals..."
              />
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>

      {/* Trading Instruments Accordion */}
      <Accordion 
        expanded={expanded.instruments} 
        onChange={handleAccordionChange('instruments')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccountBalanceIcon color="primary" />
            <Typography variant="h6">Trading Instruments (Assets)</Typography>
            {strategyConfig.symbols.length > 0 && (
              <Chip label={`${strategyConfig.symbols.length} symbols`} color="success" size="small" />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Add stocks, ETFs, or crypto symbols that your strategy will trade
          </Typography>
            <Box sx={{ mb: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={9}>
                <Autocomplete
                  freeSolo
                  options={popularSymbols}
                  value={symbolInput}
                  onInputChange={(event, newInputValue) => {
                    setSymbolInput(newInputValue);
                  }}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Add Trading Symbol"
                      placeholder="Type symbol (e.g., AAPL, BTC-USD, SPY)"
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          addSymbol();
                        }
                      }}
                    />
                  )}
                />
              </Grid>
              <Grid item xs={12} md={3}>
                <Button
                  fullWidth
                  variant="outlined"
                  onClick={addSymbol}
                  startIcon={<AddIcon />}
                >
                  Add Symbol
                </Button>
              </Grid>
            </Grid>
          </Box>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {strategyConfig.symbols.map((symbol, index) => (
              <Chip
                key={index}
                label={symbol}
                onDelete={() => removeSymbol(index)}
                color="primary"
                variant="outlined"
              />
            ))}
          </Box>

          {strategyConfig.symbols.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
              <AccountBalanceIcon sx={{ fontSize: 48, mb: 1 }} />
              <Typography variant="body2">
                No trading instruments configured. Add symbols to define what assets your strategy will trade.
              </Typography>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Technical Indicators Accordion */}
      <Accordion 
        expanded={expanded.indicators} 
        onChange={handleAccordionChange('indicators')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AssessmentIcon color="primary" />
            <Typography variant="h6">Technical Indicators</Typography>
            {strategyConfig.indicators.length > 0 && (
              <Chip label={`${strategyConfig.indicators.length} indicators`} color="success" size="small" />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Configure technical indicators that will analyze market conditions for your strategy
          </Typography>

          <Box sx={{ mb: 3 }}>
            <FormControl fullWidth sx={{ maxWidth: 300 }}>
              <InputLabel>Add Indicator</InputLabel>
              <Select
                value=""
                onChange={(e) => {
                  if (e.target.value) {
                    addIndicator(e.target.value);
                  }
                }}
                label="Add Indicator"
              >                {availableIndicators.map(indicator => (
                  <MenuItem 
                    key={indicator.name} 
                    value={indicator.name}
                  >
                    {indicator.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>

          <Grid container spacing={2}>
            {strategyConfig.indicators.map((indicator, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Card variant="outlined" sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <IndicatorIcon fontSize="small" color="primary" />
                      <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                        {indicator.name}_{indicator.params.period || Object.values(indicator.params)[0]}
                      </Typography>
                    </Box>
                    <IconButton
                      size="small"
                      onClick={() => removeIndicator(index)}
                      color="error"
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>
                  
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {Object.entries(indicator.params).map(([paramName, paramValue]) => (
                      <TextField
                        key={paramName}
                        size="small"
                        label={paramName.charAt(0).toUpperCase() + paramName.slice(1)}
                        type="number"
                        value={paramValue}
                        onChange={(e) => updateIndicatorParams(index, paramName, parseFloat(e.target.value))}
                      />
                    ))}
                  </Box>
                </Card>
              </Grid>
            ))}
          </Grid>

          {strategyConfig.indicators.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
              <IndicatorIcon sx={{ fontSize: 48, mb: 1 }} />
              <Typography variant="body2">
                No indicators configured. Add technical indicators to analyze market conditions.
              </Typography>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Entry Conditions Accordion */}
      <Accordion 
        expanded={expanded.entryConditions} 
        onChange={handleAccordionChange('entryConditions')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TrendingUpIcon color="success" />
            <Typography variant="h6">Entry Conditions</Typography>
            {strategyConfig.entry_conditions.length > 0 && (
              <Chip label={`${strategyConfig.entry_conditions.length} conditions`} color="success" size="small" />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Define the conditions that must be met to enter a trade
          </Typography>

          <Box sx={{ mb: 2 }}>
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={addEntryCondition}
              color="success"
            >
              Add Entry Condition
            </Button>
          </Box>
          
          <List sx={{ p: 0 }}>
            {strategyConfig.entry_conditions.map((condition, index) => (
              <ListItem key={index} sx={{ px: 0, py: 1 }}>
                <Grid container spacing={1} alignItems="center">
                  <Grid item xs={3}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Indicator</InputLabel>                      <Select
                        value={condition.indicator}
                        onChange={(e) => updateEntryCondition(index, 'indicator', e.target.value)}
                        label="Indicator"
                      >
                        {getAvailableIndicatorValues().map(indValue => (
                          <MenuItem key={indValue} value={indValue.toLowerCase()}>
                            {indValue}
                          </MenuItem>
                        ))}
                        {ohlcvColumns.map(col => (
                          <MenuItem key={col} value={col.toLowerCase()}>
                            {col}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={4}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Condition</InputLabel>
                      <Select
                        value={condition.comparison}
                        onChange={(e) => updateEntryCondition(index, 'comparison', e.target.value)}
                        label="Condition"
                      >
                        {comparisons.map(comp => (
                          <MenuItem key={comp} value={comp}>{comp.replace(/_/g, ' ')}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>                  <Grid item xs={3}>
                    {condition.comparison === 'between' ? (
                      <RangeValueInput
                        lowValue={condition.low_value || ''}
                        highValue={condition.high_value || ''}
                        onLowChange={(newValue) => updateEntryCondition(index, 'low_value', newValue)}
                        onHighChange={(newValue) => updateEntryCondition(index, 'high_value', newValue)}
                      />
                    ) : (
                      <ValueInput
                        value={condition.value}
                        onChange={(newValue) => updateEntryCondition(index, 'value', newValue)}
                      />
                    )}
                  </Grid>
                  <Grid item xs={2}>
                    <IconButton
                      size="small"
                      onClick={() => removeEntryCondition(index)}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Grid>
                </Grid>
              </ListItem>
            ))}
          </List>

          {strategyConfig.entry_conditions.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
              <TrendingUpIcon sx={{ fontSize: 48, mb: 1 }} />
              <Typography variant="body2">
                No entry conditions defined. Add conditions to specify when to enter trades.
              </Typography>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Exit Conditions Accordion */}
      <Accordion 
        expanded={expanded.exitConditions} 
        onChange={handleAccordionChange('exitConditions')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <TrendingDownIcon color="error" />
            <Typography variant="h6">Exit Conditions</Typography>
            {strategyConfig.exit_conditions.length > 0 && (
              <Chip label={`${strategyConfig.exit_conditions.length} conditions`} color="error" size="small" />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Define the conditions that will trigger an exit from a trade
          </Typography>

          <Box sx={{ mb: 2 }}>
            <Button
              variant="outlined"
              startIcon={<AddIcon />}
              onClick={addExitCondition}
              color="error"
            >
              Add Exit Condition
            </Button>
          </Box>
          
          <List sx={{ p: 0 }}>
            {strategyConfig.exit_conditions.map((condition, index) => (
              <ListItem key={index} sx={{ px: 0, py: 1 }}>
                <Grid container spacing={1} alignItems="center">
                  <Grid item xs={3}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Indicator</InputLabel>                      <Select
                        value={condition.indicator}
                        onChange={(e) => updateExitCondition(index, 'indicator', e.target.value)}
                        label="Indicator"
                      >
                        {getAvailableIndicatorValues().map(indValue => (
                          <MenuItem key={indValue} value={indValue.toLowerCase()}>
                            {indValue}
                          </MenuItem>
                        ))}
                        {ohlcvColumns.map(col => (
                          <MenuItem key={col} value={col.toLowerCase()}>
                            {col}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={4}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Condition</InputLabel>
                      <Select
                        value={condition.comparison}
                        onChange={(e) => updateExitCondition(index, 'comparison', e.target.value)}
                        label="Condition"
                      >
                        {comparisons.map(comp => (
                          <MenuItem key={comp} value={comp}>{comp.replace(/_/g, ' ')}</MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>                  <Grid item xs={3}>
                    {condition.comparison === 'between' ? (
                      <RangeValueInput
                        lowValue={condition.low_value || ''}
                        highValue={condition.high_value || ''}
                        onLowChange={(newValue) => updateExitCondition(index, 'low_value', newValue)}
                        onHighChange={(newValue) => updateExitCondition(index, 'high_value', newValue)}
                      />
                    ) : (
                      <ValueInput
                        value={condition.value}
                        onChange={(newValue) => updateExitCondition(index, 'value', newValue)}
                      />
                    )}
                  </Grid>
                  <Grid item xs={2}>
                    <IconButton
                      size="small"
                      onClick={() => removeExitCondition(index)}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Grid>
                </Grid>
              </ListItem>
            ))}
          </List>

          {strategyConfig.exit_conditions.length === 0 && (
            <Box sx={{ textAlign: 'center', py: 4, color: 'text.secondary' }}>
              <TrendingDownIcon sx={{ fontSize: 48, mb: 1 }} />
              <Typography variant="body2">
                No exit conditions defined. Add conditions to specify when to exit trades.
              </Typography>
            </Box>
          )}
        </AccordionDetails>
      </Accordion>

      {/* Risk Management Accordion */}
      <Accordion 
        expanded={expanded.riskManagement} 
        onChange={handleAccordionChange('riskManagement')}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SettingsIcon color="warning" />
            <Typography variant="h6">Risk Management & Position Sizing</Typography>
            <Chip label="Configured" color="success" size="small" />
            {strategyConfig.dollar_cost_averaging.enabled && (
              <Chip label="DCA Enabled" color="info" size="small" />
            )}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Configure position sizing, risk parameters, and dollar cost averaging to protect your capital
          </Typography>
          
          {/* Basic Risk Management Section */}
          <Typography variant="h6" sx={{ mb: 2, color: 'primary.main' }}>
            Basic Risk Management
          </Typography>
          
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} md={6}>
              <FormControl fullWidth>
                <InputLabel>Position Sizing Method</InputLabel>
                <Select
                  value={strategyConfig.risk_management.position_sizing_method}
                  onChange={(e) => setStrategyConfig({
                    ...strategyConfig,
                    risk_management: {
                      ...strategyConfig.risk_management,
                      position_sizing_method: e.target.value
                    }
                  })}
                  label="Position Sizing Method"
                >
                  <MenuItem value="risk_based">Risk Based</MenuItem>
                  <MenuItem value="percentage">Percentage of Capital</MenuItem>
                  <MenuItem value="fixed">Fixed Amount</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="Risk per Trade (%)"
                type="number"
                value={(strategyConfig.risk_management.risk_per_trade * 100).toFixed(1)}
                onChange={(e) => setStrategyConfig({
                  ...strategyConfig,
                  risk_management: {
                    ...strategyConfig.risk_management,
                    risk_per_trade: parseFloat(e.target.value) / 100
                  }
                })}
                inputProps={{ min: 0.1, max: 10, step: 0.1 }}
                helperText="Percentage of capital to risk per trade"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Stop Loss (%)"
                type="number"
                value={(strategyConfig.risk_management.stop_loss * 100).toFixed(1)}
                onChange={(e) => setStrategyConfig({
                  ...strategyConfig,
                  risk_management: {
                    ...strategyConfig.risk_management,
                    stop_loss: parseFloat(e.target.value) / 100
                  }
                })}
                inputProps={{ min: 0.5, max: 20, step: 0.1 }}
                helperText="Maximum loss per trade"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Take Profit (%)"
                type="number"
                value={(strategyConfig.risk_management.take_profit * 100).toFixed(1)}
                onChange={(e) => setStrategyConfig({
                  ...strategyConfig,
                  risk_management: {
                    ...strategyConfig.risk_management,
                    take_profit: parseFloat(e.target.value) / 100
                  }
                })}
                inputProps={{ min: 1, max: 50, step: 0.1 }}
                helperText="Target profit per trade"
              />
            </Grid>
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Max Position Size ($)"
                type="number"
                value={strategyConfig.risk_management.max_position_size}
                onChange={(e) => setStrategyConfig({
                  ...strategyConfig,
                  risk_management: {
                    ...strategyConfig.risk_management,
                    max_position_size: parseFloat(e.target.value)
                  }
                })}
                inputProps={{ min: 100, step: 100 }}
                helperText="Maximum position size in dollars"
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                fullWidth
                label="ATR Multiplier"
                type="number"
                value={strategyConfig.risk_management.atr_multiplier}
                onChange={(e) => setStrategyConfig({
                  ...strategyConfig,
                  risk_management: {
                    ...strategyConfig.risk_management,
                    atr_multiplier: parseFloat(e.target.value)
                  }
                })}
                inputProps={{ min: 0.5, max: 5, step: 0.1 }}
                helperText="ATR multiplier for volatility-based sizing"
              />
            </Grid>
          </Grid>

          {/* Dollar Cost Averaging Section */}
          <Box sx={{ borderTop: 1, borderColor: 'divider', pt: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
              <Typography variant="h6" sx={{ color: 'info.main' }}>
                Dollar Cost Averaging (DCA)
              </Typography>
              <Button
                variant={strategyConfig.dollar_cost_averaging.enabled ? "contained" : "outlined"}
                color={strategyConfig.dollar_cost_averaging.enabled ? "success" : "primary"}
                size="small"
                onClick={() => setStrategyConfig({
                  ...strategyConfig,
                  dollar_cost_averaging: {
                    ...strategyConfig.dollar_cost_averaging,
                    enabled: !strategyConfig.dollar_cost_averaging.enabled
                  }
                })}
              >
                {strategyConfig.dollar_cost_averaging.enabled ? "Enabled" : "Disabled"}
              </Button>
            </Box>

            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {strategyConfig.dollar_cost_averaging.enabled 
                ? "DCA allows multiple positions per symbol to scale into trades at different price levels"
                : "Enable DCA to allow multiple positions per symbol for scaling into trades"
              }
            </Typography>

            {strategyConfig.dollar_cost_averaging.enabled && (
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    label="Maximum Positions per Symbol"
                    type="number"
                    value={strategyConfig.dollar_cost_averaging.max_positions}
                    onChange={(e) => setStrategyConfig({
                      ...strategyConfig,
                      dollar_cost_averaging: {
                        ...strategyConfig.dollar_cost_averaging,
                        max_positions: parseInt(e.target.value)
                      }
                    })}
                    inputProps={{ min: 1, max: 10, step: 1 }}
                    helperText="Maximum number of simultaneous positions per symbol"
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <Box sx={{ 
                    p: 2, 
                    bgcolor: 'info.light', 
                    borderRadius: 1, 
                    color: 'info.contrastText' 
                  }}>
                    <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                      DCA Strategy Info:
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      • When enabled, strategy can open multiple trades per symbol at different price levels
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      • Each entry signal creates a new position (up to max limit)
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      • Positions are closed individually based on exit conditions
                    </Typography>
                    <Typography variant="caption" sx={{ display: 'block' }}>
                      • Useful for scaling into positions during favorable conditions
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            )}
          </Box>
        </AccordionDetails>
      </Accordion>

      {/* Action Buttons */}
      <Box sx={{ mt: 3, p: 3, bgcolor: 'background.paper', borderRadius: 2, border: 1, borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
          <Button
            variant="outlined"
            startIcon={<CodeIcon />}
            onClick={() => setIsCodeViewOpen(true)}
          >
            View Code
          </Button>
          <Button
            variant="outlined"
            startIcon={<PlayArrowIcon />}
            color="primary"
          >
            Test Strategy
          </Button>
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={handleSaveStrategy}
            disabled={!user}
          >          Save Strategy
          </Button>
        </Box>
      </Box>

      {/* Code View Dialog */}
      <Dialog
        open={isCodeViewOpen}
        onClose={() => setIsCodeViewOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Strategy Configuration (YAML)</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            multiline
            rows={20}
            value={yamlConfig}
            onChange={(e) => setYamlConfig(e.target.value)}
            variant="outlined"
            sx={{ 
              '& .MuiInputBase-input': { 
                fontFamily: 'monospace',
                fontSize: '0.875rem'
              }
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIsCodeViewOpen(false)}>Close</Button>
          <Button variant="contained">Save Changes</Button>
        </DialogActions>
      </Dialog>

      {/* Success/Error Snackbar */}
      <Snackbar
        open={saveSuccess}
        autoHideDuration={6000}
        onClose={() => setSaveSuccess(false)}
      >
        <Alert onClose={() => setSaveSuccess(false)} severity="success">
          Strategy saved successfully!
        </Alert>
      </Snackbar>

      <Snackbar
        open={!!saveError}
        autoHideDuration={6000}
        onClose={() => setSaveError('')}
      >
        <Alert onClose={() => setSaveError('')} severity="error">
          {saveError}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default StrategyBuilderInterface;
