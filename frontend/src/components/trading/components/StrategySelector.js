import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Chip,
  Alert,
  CircularProgress,
  Autocomplete,
  TextField
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon
} from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
import { useStrategy } from '../../../context/StrategyContext';
import { useDeployedStrategy } from '../../../context/DeployedStrategyContext';
import { deployStrategy, stopStrategy } from '../../../api/Client';

const transformDefaultStrategies = (backendStrategies) => {
  return backendStrategies.map((strategy, index) => {
    const indicators = strategy.config?.indicators?.map(ind => ind.name) || [];
    
    // Determine category based on strategy name/indicators
    let category = 'Trading';
    if (strategy.name.toLowerCase().includes('ema') || strategy.name.toLowerCase().includes('crossover')) {
      category = 'Trend Following';
    } else if (strategy.name.toLowerCase().includes('bollinger')) {
      category = 'Breakout';
    } else if (strategy.name.toLowerCase().includes('macd')) {
      category = 'Momentum';
    } else if (strategy.name.toLowerCase().includes('rsi')) {
      category = 'Mean Reversion';
    }
    
    // Determine complexity based on number of indicators and conditions
    let complexity = 'Beginner';
    const totalConditions = (strategy.config?.entry_conditions?.length || 0) + 
                          (strategy.config?.exit_conditions?.length || 0);
    if (totalConditions > 3 || indicators.length > 2) {
      complexity = 'Advanced';
    } else if (totalConditions > 1 || indicators.length > 1) {
      complexity = 'Intermediate';
    }
    
    return {
      id: `default_${index + 1}`,
      name: strategy.name,
      description: strategy.description || 'No description provided',
      type: 'default',
      category,
      performance: 'N/A',
      complexity,
      indicators,
      timeframes: strategy.config?.timeframe ? [strategy.config.timeframe.toUpperCase()] : ['1D'],
      backtestReturn: null,
      sharpeRatio: null,
      maxDrawdown: null,
      winRate: null,
      totalTrades: null,
      config: strategy.config
    };
  });
};

const StrategySelector = ({ mode = 'paper' }) => {
  const [searchParams] = useSearchParams();
  
  // Get strategies from StrategyContext
  const { 
    strategies, 
    defaultStrategies
  } = useStrategy();
  
  // Get deployment state from DeployedStrategyContext
  const {
    deployedStrategy,
    isDeployed,
    dataProvider,
    deploymentTime,
    activeTaskId,
    stopStrategy: stopStrategyContext,
    setDataProvider,
    setDeploymentState,
    socketStatus,
    socketError
  } = useDeployedStrategy();
  
  // Local state for UI
  const [selectedStrategy, setSelectedStrategy] = useState(deployedStrategy);
  const [isLoading, setIsLoading] = useState(false);
  const [initialCapital, setInitialCapital] = useState(100000);
  
  // Sync selectedStrategy with deployedStrategy from context
  useEffect(() => {
    if (deployedStrategy && !selectedStrategy) {
      setSelectedStrategy(deployedStrategy);
    }
  }, [deployedStrategy, selectedStrategy]);
  
  // Combine and format all strategies
  const allStrategies = useMemo(() => {
    const transformedDefaultStrategies = transformDefaultStrategies(defaultStrategies);
    
    const userStrategiesFormatted = strategies.map(strategy => ({
      id: strategy.id || strategy._id,
      name: strategy.name,
      description: strategy.description || 'No description provided',
      type: 'user',
      category: 'Custom',
      performance: 'N/A',
      complexity: 'Custom',
      indicators: strategy.config?.indicators?.map(ind => ind.name) || [],
      timeframes: strategy.config?.timeframe ? [strategy.config.timeframe] : [],
      backtestReturn: null,
      sharpeRatio: null,
      maxDrawdown: null,
      winRate: null,
      totalTrades: null,
      createdAt: strategy.created_at
    }));

    return [...transformedDefaultStrategies, ...userStrategiesFormatted];
  }, [strategies, defaultStrategies]);

  const handleDeployStrategy = async () => {
    if (!selectedStrategy) {
      alert('Please select a strategy first');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const result = await deployStrategy(selectedStrategy.id, mode, dataProvider, initialCapital);
      if (!result.success) {
        console.error("Deployment failed:", result.error);
        alert(`Deployment failed: ${result.error}`);
      } else {
        const taskId = result.data.task_id;
        if (!taskId) {
          console.error("Warning: No task_id returned from deployment response");
        }
        setDeploymentState(selectedStrategy, taskId, dataProvider, mode);
        console.log('Strategy deployed successfully, task ID:', taskId);
      }
    } catch (error) {
      console.error('Deployment error:', error);
      alert(`Deployment failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopStrategy = async () => {
    if (!selectedStrategy) {
      alert('No strategy is currently selected to be stopped.');
      return;
    }

    if (!activeTaskId) {
      alert('No active task ID found for the running strategy.');
      return;
    }

    setIsLoading(true);

    try {
      const result = await stopStrategy(selectedStrategy.id, activeTaskId);

      if (result.success) {
        stopStrategyContext();
        console.log('Stop command sent successfully.');
      } else {
        console.error('Failed to stop strategy:', result.error);
        alert(`Failed to stop strategy: ${result.error}`);
      }
    } catch (error) {
      console.error('Stopping error:', error);
      alert(`An unexpected error occurred while stopping the strategy: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDataProviderChange = (event) => {
    const newProvider = event.target.value;
    setDataProvider(newProvider);
  };

  return (
    <>
      {/* Show alert if strategy was pre-selected */}
      {selectedStrategy && searchParams.get('strategyData') && (
        <Alert severity="success" sx={{ mb: 3 }}>
          Strategy "<strong>{selectedStrategy.name}</strong>" has been pre-loaded from the Strategy Library and is ready to deploy!
        </Alert>
      )}

      {/* Show alert if deployment was restored from localStorage */}
      {isDeployed && deploymentTime && (
        <Alert severity="info" sx={{ mb: 3 }}>
          Deployment restored: Strategy "<strong>{deployedStrategy?.name}</strong>" has been running since {new Date(deploymentTime).toLocaleString()}
        </Alert>
      )}

      <Accordion defaultExpanded sx={{ mb: 3 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
            <Typography variant="h6">Strategy Deployment</Typography>
            {isDeployed && <Chip label="ACTIVE" color="success" size="small" sx={{ ml: 'auto', mr: 2 }} />}
          </Box>
        </AccordionSummary>
        <AccordionDetails>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center' }}>
            <Box sx={{ flex: '1 1 300px', minWidth: '250px' }}>
              <Autocomplete
                options={allStrategies}
                getOptionLabel={(option) => option.name}
                value={selectedStrategy}
                onChange={(event, newValue) => {
                  setSelectedStrategy(newValue);
                }}
                disabled={isDeployed}
                renderInput={(params) => <TextField {...params} label="Select Strategy" />}
                renderOption={(props, option) => (
                  <li {...props}>
                    <Box>
                      <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                        {option.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {option.category} • {option.type === 'user' ? 'Custom' : 'Default'}
                      </Typography>
                    </Box>
                  </li>
                )}
              />
            </Box>
            <Box sx={{ flex: '1 1 150px', minWidth: '120px' }}>
              <FormControl fullWidth size="small">
                <InputLabel>Data Provider</InputLabel>
                <Select
                  value={dataProvider}
                  label="Data Provider"
                  onChange={handleDataProviderChange}
                  disabled={isDeployed}
                >
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="polygon">Polygon</MenuItem>
                  <MenuItem value="yahoo">Yahoo</MenuItem>
                </Select>
              </FormControl>
            </Box>
            <Box sx={{ flex: '1 1 150px', minWidth: '120px' }}>
              <TextField
                fullWidth
                size="small"
                label="Initial Capital"
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                disabled={isDeployed}
                InputProps={{
                  startAdornment: <Typography sx={{ mr: 0.5, color: 'text.secondary' }}>$</Typography>,
                }}
                inputProps={{ min: 0, step: 1000 }}
              />
            </Box>
            <Box sx={{ flex: '1 1 320px', minWidth: '320px', display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                fullWidth
                startIcon={<PlayArrowIcon />}
                onClick={handleDeployStrategy}
                disabled={isLoading || isDeployed || !selectedStrategy}
                color="primary"
                sx={{ height: 56 }}
              >
                Deploy Strategy
              </Button>
              <Button
                variant="contained"
                fullWidth
                startIcon={<StopIcon />}
                onClick={handleStopStrategy}
                disabled={isLoading || !isDeployed}
                color="error"
                sx={{ height: 56 }}
              >
                Stop Strategy
              </Button>
            </Box>
          </Box>
          
          {/* Deployment Status */}
          {selectedStrategy && (
            <Box sx={{ mt: 2 }}>
              {socketError && (
                <Alert severity="error" sx={{ mb: 1 }}>
                  <strong>Connection Error:</strong> {socketError}
                </Alert>
              )}
              {!socketError && socketStatus === 'connecting' && (
                <Alert severity="info" icon={<CircularProgress size={20} />} sx={{ mb: 1 }}>
                  Connecting to trading service...
                </Alert>
              )}
              {!socketError && (isDeployed || socketStatus === 'connected') && (
                <Alert severity="success" sx={{ mb: 1 }}>
                  <strong>Strategy "{selectedStrategy.name}" is active.</strong> Real-time logs and performance data are being streamed.
                </Alert>
              )}
              {!socketError && socketStatus === 'disconnected' && isDeployed && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  Connection lost. Attempting to reconnect...
                </Alert>
              )}
            </Box>
          )}
        </AccordionDetails>
      </Accordion>
    </>
  );
};

export default StrategySelector;
