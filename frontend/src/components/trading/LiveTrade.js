// src/components/trading/LiveTradingPage.js
import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Typography,
  useTheme,
  Container,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Grid,
  Paper,
  Chip,
  Alert,
  CircularProgress,
  Autocomplete,
  TextField,
  Stack
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  TrendingUp as TrendingUpIcon
} from '@mui/icons-material';
import { useLocation, useSearchParams } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import Plot from 'react-plotly.js';
import { useStrategy } from '../../context/StrategyContext';
import {
  fetchDefaultStrategies,
  deployStrategy,
  stopStrategy,
} from '../../api/Client';
import { useDeployedStrategy } from '../../context/DeployedStrategyContext';

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
      performance: 'N/A', // Will be populated after backtesting
      complexity,
      indicators,
      timeframes: strategy.config?.timeframe ? [strategy.config.timeframe.toUpperCase()] : ['1D'],
      backtestReturn: null,
      sharpeRatio: null,
      maxDrawdown: null,
      winRate: null,
      totalTrades: null,
      config: strategy.config // Store original config for potential use
    };
  });
};


const LiveTradingPage = () => {
  const theme = useTheme();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  
  // Get everything we need from StrategyContext
  const { 
    strategies, 
    defaultStrategies, 
    loading: strategiesLoading, 
    error: strategiesError,
    refreshStrategies 
  } = useStrategy();
  
  // Access Global Context
  const {
    deployedStrategy,
    isDeployed,
    mode, // Check if we are in 'live' mode
    deployStrategy: contextDeploy,
    stopStrategy: contextStop,
    // Data from socket
    logs,
    socketStatus,
    socketError,
    trades: liveTrades,
    metrics,
    positions
  } = useDeployedStrategy();

  // Local state for setup only
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [dataProvider, setDataProvider] = useState('alpaca');
  const [isLoading, setIsLoading] = useState(false);

  const handleDataProviderChange = (event) => {
    setDataProvider(event.target.value);
  };

  // Sync: If a LIVE strategy is already deployed globally, show it
  useEffect(() => {
    if (isDeployed && mode === 'live' && deployedStrategy) {
      setSelectedStrategy(deployedStrategy);
    }
  }, [isDeployed, mode, deployedStrategy]);

  // Handle pre-selected strategy from URL parameters
  useEffect(() => {
    const preSelectedStrategyData = searchParams.get('strategyData');
    if (preSelectedStrategyData) {
      try {
        const strategyData = JSON.parse(preSelectedStrategyData);
        setSelectedStrategy(strategyData);
        console.log('Pre-selected strategy loaded:', strategyData);
      } catch (error) {
        console.error('Error parsing pre-selected strategy data:', error);
      }
    }
  }, [searchParams]);

  // Combine and format all strategies
  const allStrategies = useMemo(() => {
    // Transform default strategies
    const transformedDefaultStrategies = transformDefaultStrategies(defaultStrategies);
    
    // Format user strategies
    const userStrategiesFormatted = strategies.map(strategy => ({
      id: strategy.id,
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
      const result = await deployStrategy(selectedStrategy.id, 'live', dataProvider);
      if (result.success) {
        // Tell context to start listening (this starts the socket)
        contextDeploy(selectedStrategy, dataProvider, 'live'); 
      } else {
        alert(`Deployment failed: ${result.error}`);
      }
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleStopStrategy = async () => {
    if (!selectedStrategy) {
      alert('No strategy is currently selected to be stopped.');
      return;
    }

    setIsLoading(true);

    try {
      const result = await stopStrategy(selectedStrategy.id);

      if (result.success) {
        contextStop(); // Tell context to stop listening
        console.log('Stop command sent successfully.');
      } else {
        console.error('Failed to stop strategy:', result.error);
        alert(`Failed to stop strategy: ${result.error}`);
      }
    } catch (error) {
      console.error('Stopping error:', error);
      alert(
        `An unexpected error occurred while stopping the strategy: ${error.message}`
      );
    } finally {
      setIsLoading(false);
    }
  };

  const tradeColumns = [
    { field: 'id', headerName: 'ID', width: 70 },
    { field: 'symbol', headerName: 'Symbol', width: 100 },
    { field: 'side', headerName: 'Side', width: 80, renderCell: (params) => (<Chip label={params.value} color={params.value === 'BUY' ? 'success' : 'error'} size="small"/>) },
    { field: 'quantity', headerName: 'Quantity', width: 100, type: 'number' },
    { field: 'entryPrice', headerName: 'Entry Price', width: 120, type: 'number', valueFormatter: (params) => `$${params.value?.toFixed(2) || 'N/A'}` },
    { field: 'exitPrice', headerName: 'Exit Price', width: 120, type: 'number', valueFormatter: (params) => `$${params.value?.toFixed(2) || 'N/A'}` },
    { field: 'entryTime', headerName: 'Entry Time', width: 180, type: 'dateTime', valueFormatter: (params) => params.value?.toLocaleString() || 'N/A' },
    { field: 'exitTime', headerName: 'Exit Time', width: 180, type: 'dateTime', valueFormatter: (params) => params.value?.toLocaleString() || 'N/A' },
    { field: 'pnl', headerName: 'P&L', width: 120, type: 'number', renderCell: (params) => (<Typography variant="body2" sx={{ color: params.value >= 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>${params.value?.toFixed(2) || '0.00'}</Typography>) },
    { field: 'status', headerName: 'Status', width: 100, renderCell: (params) => (<Chip label={params.value} color={params.value === 'OPEN' ? 'warning' : 'default'} size="small"/>) }
  ];

  const pnlPlotData = [{ x: logs.map(d => d.timestamp), y: logs.map(d => d.value), type: 'scatter', mode: 'lines', name: 'P&L', line: { color: logs.length > 0 ? (logs[logs.length - 1].value >= 0 ? theme.palette.success.main : theme.palette.error.main) : theme.palette.text.secondary, width: 2 } }];
  const pnlPlotLayout = { title: 'Live P&L', xaxis: { title: 'Time' }, yaxis: { title: 'P&L ($)', tickformat: '$,.0f' }, plot_bgcolor: theme.palette.background.paper, paper_bgcolor: theme.palette.background.paper, font: { color: theme.palette.text.primary }, margin: { l: 60, r: 30, b: 50, t: 50 } };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 700, mb: 3 }}>
        <TrendingUpIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Live Trading
      </Typography>

      {/* Show alert if strategy was pre-selected */}
      {selectedStrategy && searchParams.get('strategyData') && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          Strategy "<strong>{selectedStrategy.name}</strong>" has been pre-loaded from the Strategy Library and is ready to deploy for <strong>LIVE TRADING</strong>!
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
              />
            </Box>
            <Box sx={{ flex: '1 1 150px', minWidth: '120px' }}>
              <FormControl fullWidth>
                <InputLabel>Data Provider</InputLabel>
                <Select
                  value={dataProvider}
                  onChange={handleDataProviderChange}
                  label="Data Provider"
                  disabled={isDeployed}
                >
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="polygon">Polygon</MenuItem>
                </Select>
              </FormControl>
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
            {isDeployed && (
              <Box sx={{ width: '100%', mt: 2 }}>
                <Alert severity="info">Current P&L: <strong>${logs.length > 0 ? logs[logs.length - 1].value : '0.00'}</strong></Alert>
              </Box>
            )}
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

      {/* Strategy Performance, Trading Logs, and Current Positions */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <Paper sx={{ p: 2, height: 400 }}>
          <Typography variant="h6" gutterBottom>Strategy Performance</Typography>
          {isDeployed && logs.length > 1 ? (<Plot data={pnlPlotData} layout={pnlPlotLayout} style={{ width: '100%', height: '320px' }} config={{ responsive: true, displaylogo: false }}/>) : (<Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '320px', color: theme.palette.text.secondary }}>Deploy a strategy to see live performance</Box>)}
        </Paper>
        <Paper sx={{ p: 2, height: 400, display: 'flex', flexDirection: 'column' }}>
          <Typography variant="h6" gutterBottom>Trading Logs</Typography>
          <Box sx={{ flexGrow: 1, overflow: 'auto', border: `1px solid ${theme.palette.divider}`, borderRadius: 1, p: 1, backgroundColor: theme.palette.background.default }}>
            {socketError && <Alert severity="error">{socketError}</Alert>}
            {logs.map((log, index) => (
              <Box key={index} sx={{ mb: 0.5, fontSize: '0.875rem', fontFamily: 'monospace' }}>
                <Typography component="span" variant="body2" sx={{ color: theme.palette.text.secondary }}>{new Date(log.timestamp).toLocaleTimeString()}</Typography>
                <Typography component="span" variant="body2" sx={{ color: log.level === 'WARNING' ? theme.palette.warning.main : theme.palette.info.main, mx: 1 }}>[{log.level}]</Typography>
                <Typography component="span" variant="body2">{log.message}</Typography>
              </Box>
            ))}
            {logs.length === 0 && !socketError && (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: theme.palette.text.secondary }}>
                Waiting for logs...
              </Box>
            )}
          </Box>
        </Paper>
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>Current Positions</Typography>
          <Box sx={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.palette.text.secondary, border: `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
            {/* You can map over your positions data here to render a table or list */}
            No open positions
          </Box>
        </Paper>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>Trade History</Typography>
        <Box sx={{ height: 400, width: '100%' }}>
          <DataGrid rows={isDeployed ? liveTrades : []} columns={tradeColumns} pageSize={5} rowsPerPageOptions={[5]} disableSelectionOnClick sx={{ '& .MuiDataGrid-cell': { borderColor: theme.palette.divider }, '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider } }} />
        </Box>
      </Paper>
    </Container>
  );
};

export default LiveTradingPage;