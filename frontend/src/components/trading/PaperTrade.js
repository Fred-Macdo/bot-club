// src/components/trading/PaperTradingPage.js
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
  Assessment as AssessmentIcon
} from '@mui/icons-material';
import { useLocation, useSearchParams } from 'react-router-dom';
import { DataGrid } from '@mui/x-data-grid';
import Plot from 'react-plotly.js';
import { useStrategy } from '../../context/StrategyContext';
import { useDeployedStrategy } from '../../context/DeployedStrategyContext';
import {
  fetchDefaultStrategies,
  deployStrategy,
  stopStrategy,
} from '../../api/Client';
import useTradingSocket from '../../hooks/useTradingSocket';

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


const PaperTradingPage = () => {
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
  
  // Get deployment state from context
  const {
    deployedStrategy,
    isDeployed,
    dataProvider,
    deploymentTime,
    deployStrategy: deployStrategyContext,
    stopStrategy: stopStrategyContext,
    setDataProvider
  } = useDeployedStrategy();
  
  // Local state for UI
  const [selectedStrategy, setSelectedStrategy] = useState(deployedStrategy);
  const [isLoading, setIsLoading] = useState(false);
  const [pnlData, setPnlData] = useState([]); // Add this line
  const [currentPnL, setCurrentPnL] = useState(0); // Add this line
  const [positions, setPositions] = useState([]); // Add state for positions

  const handleDataProviderChange = (event) => {
    setDataProvider(event.target.value);
  };

  // Sync selectedStrategy with deployedStrategy from context
  useEffect(() => {
    if (deployedStrategy && !selectedStrategy) {
      setSelectedStrategy(deployedStrategy);
      console.log('Restored deployed strategy from context:', deployedStrategy.name);
    }
  }, [deployedStrategy, selectedStrategy]);
  
  // State from our new WebSocket hook
  const { 
    logs, 
    status: socketStatus, 
    error: socketError,
    trades: liveTrades,
    completedTrades,
    positions: wsPositions, // Renamed to avoid conflict with local state
    metrics 
  } = useTradingSocket(isDeployed ? selectedStrategy?.id : null);

  // Update P&L data and current P&L when metrics change
  useEffect(() => {
    if (metrics) {
      setCurrentPnL(metrics.totalPnL || 0);
      setPnlData(prev => [
        ...prev,
        {
          timestamp: new Date(metrics.timestamp),
          value: metrics.totalPnL || 0
        }
      ].slice(-100)); // Keep last 100 data points
    }
  }, [metrics]);

  // Update positions state when websocket data changes
  useEffect(() => {
    if (wsPositions) {
      setPositions(wsPositions);
    }
  }, [wsPositions]);

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
      const result = await deployStrategy(selectedStrategy.id, 'paper', dataProvider);
      if (!result.success) {
        console.error("Deployment failed:", result.error);
        alert(`Deployment failed: ${result.error}`);
      } else {
        // Save to context (which persists to localStorage)
        deployStrategyContext(selectedStrategy, dataProvider);
        console.log('Strategy deployed successfully');
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

    setIsLoading(true);

    try {
      const result = await stopStrategy(selectedStrategy.id);

      if (result.success) {
        // Update context (which persists to localStorage)
        stopStrategyContext();   
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
    { 
      field: 'side', 
      headerName: 'Side', 
      width: 80, 
      renderCell: (params) => {
        if (!params || !params.value) return null;
        return <Chip label={params.value} color={params.value === 'BUY' ? 'success' : 'error'} size="small"/>;
      }
    },
    { 
      field: 'quantity', 
      headerName: 'Quantity', 
      width: 100, 
      type: 'number',
      valueFormatter: (params) => {
        if (!params || params.value == null || params.value === undefined) return 'N/A';
        try {
          return Number(params.value).toFixed(2);
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'entryPrice', 
      headerName: 'Entry Price', 
      width: 120, 
      type: 'number', 
      valueFormatter: (params) => {
        if (!params || params.value == null || params.value === undefined) return 'N/A';
        try {
          return `$${Number(params.value).toFixed(2)}`;
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'exitPrice', 
      headerName: 'Exit Price', 
      width: 120, 
      type: 'number', 
      valueFormatter: (params) => {
        if (!params || params.value == null || params.value === undefined) return 'N/A';
        try {
          return `$${Number(params.value).toFixed(2)}`;
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'entryTime', 
      headerName: 'Entry Time', 
      width: 180, 
      type: 'dateTime', 
      valueGetter: (params) => {
        if (!params || !params.row || params.row.entryTime == null) return null;
        try {
          return new Date(params.row.entryTime);
        } catch {
          return null;
        }
      },
      valueFormatter: (params) => {
        if (!params || params.value == null || params.value === undefined) return 'N/A';
        try {
          return params.value.toLocaleString();
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'exitTime', 
      headerName: 'Exit Time', 
      width: 180, 
      type: 'dateTime', 
      valueGetter: (params) => {
        if (!params || !params.row || params.row.exitTime == null) return null;
        try {
          return new Date(params.row.exitTime);
        } catch {
          return null;
        }
      },
      valueFormatter: (params) => {
        if (!params || params.value == null || params.value === undefined) return 'N/A';
        try {
          return params.value.toLocaleString();
        } catch {
          return 'N/A';
        }
      }
    },
    { 
      field: 'pnl', 
      headerName: 'P&L', 
      width: 120, 
      type: 'number', 
      renderCell: (params) => {
        if (!params || params.value == null || params.value === undefined) {
          return <Typography variant="body2">N/A</Typography>;
        }
        try {
          const pnlValue = Number(params.value);
          return (
            <Typography 
              variant="body2" 
              sx={{ 
                color: pnlValue >= 0 ? theme.palette.success.main : theme.palette.error.main, 
                fontWeight: 'bold' 
              }}
            >
              ${pnlValue.toFixed(2)}
            </Typography>
          );
        } catch {
          return <Typography variant="body2">N/A</Typography>;
        }
      }
    },
    { 
      field: 'status', 
      headerName: 'Status', 
      width: 100, 
      renderCell: (params) => {
        if (!params) return null;
        const status = params.value || 'PENDING';
        return (
          <Chip 
            label={status} 
            color={status === 'CLOSED' ? 'default' : status === 'FILLED' ? 'success' : 'warning'} 
            size="small"
          />
        );
      }
    }
  ];

  const pnlPlotData = [{ x: pnlData.map(d => d.timestamp), y: pnlData.map(d => d.value), type: 'scatter', mode: 'lines', name: 'P&L', line: { color: currentPnL >= 0 ? theme.palette.success.main : theme.palette.error.main, width: 2 } }];
  const pnlPlotLayout = { title: 'Paper Trading P&L', xaxis: { title: 'Time' }, yaxis: { title: 'P&L ($)', tickformat: '$,.0f' }, plot_bgcolor: theme.palette.background.paper, paper_bgcolor: theme.palette.background.paper, font: { color: theme.palette.text.primary }, margin: { l: 60, r: 30, b: 50, t: 50 } };

  const positionColumns = [
    { field: 'symbol', headerName: 'Symbol', width: 130 },
    { field: 'quantity', headerName: 'Quantity', width: 130, type: 'number' },
    { 
      field: 'avgEntryPrice', 
      headerName: 'Avg. Entry Price', 
      width: 150, 
      type: 'number',
      valueFormatter: (value) => value ? `$${Number(value).toFixed(4)}` : 'N/A'
    },
    { 
      field: 'marketPrice', 
      headerName: 'Market Price', 
      width: 150, 
      type: 'number',
      valueFormatter: (value) => value ? `$${Number(value).toFixed(4)}` : 'N/A'
    },
    { 
      field: 'marketValue', 
      headerName: 'Market Value', 
      width: 150, 
      type: 'number',
      valueFormatter: (value) => value ? `$${Number(value).toFixed(2)}` : 'N/A'
    },
    { 
      field: 'unrealizedPnl', 
      headerName: 'Unrealized P&L', 
      width: 160, 
      type: 'number',
      renderCell: (params) => {
        const pnl = Number(params.value) || 0;
        const color = pnl >= 0 ? theme.palette.success.main : theme.palette.error.main;
        return (
          <Typography variant="body2" sx={{ color: color, fontWeight: 'bold' }}>
            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
          </Typography>
        );
      }
    },
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom sx={{ color: theme.palette.primary.main, fontWeight: 700, mb: 3 }}>
        <AssessmentIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
        Paper Trading
      </Typography>

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
                <Alert severity="info">Current P&L: <strong>${currentPnL.toFixed(2)}</strong></Alert>
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

      {/* Performance Metrics */}
      {metrics && isDeployed && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" gutterBottom>Performance Metrics</Typography>
          <Grid container spacing={2}>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ color: metrics.totalPnL >= 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                  ${metrics.totalPnL?.toFixed(2) || '0.00'}
                </Typography>
                <Typography variant="caption" color="text.secondary">Total P&L</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold' }}>{metrics.totalTrades || 0}</Typography>
                <Typography variant="caption" color="text.secondary">Total Trades</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.info.main }}>
                  {metrics.winRate?.toFixed(1) || '0.0'}%
                </Typography>
                <Typography variant="caption" color="text.secondary">Win Rate</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                  {metrics.winningTrades || 0}
                </Typography>
                <Typography variant="caption" color="text.secondary">Winning</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                  {metrics.losingTrades || 0}
                </Typography>
                <Typography variant="caption" color="text.secondary">Losing</Typography>
              </Box>
            </Grid>
            <Grid item xs={6} sm={4} md={2}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                  ${metrics.accountValue?.toFixed(2) || '0.00'}
                </Typography>
                <Typography variant="caption" color="text.secondary">Account Value</Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}
     
      {/* Strategy Performance, Trading Logs, and Current Positions */}
      <Stack spacing={3} sx={{ mb: 3 }}>
        <Paper sx={{ p: 2, height: 400 }}>
          <Typography variant="h6" gutterBottom>Strategy Performance</Typography>
          {isDeployed && pnlData.length > 1 ? (<Plot data={pnlPlotData} layout={pnlPlotLayout} style={{ width: '100%', height: '320px' }} config={{ responsive: true, displaylogo: false }}/>) : (<Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '320px', color: theme.palette.text.secondary }}>Deploy a strategy to see paper trading performance</Box>)}
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
        
        {/* Current Positions Panel */}
        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>Current Positions</Typography>
          <Box sx={{ height: 250, width: '100%' }}>
            <DataGrid
              rows={positions}
              columns={positionColumns}
              getRowId={(row) => row.symbol} // Use symbol as the unique ID
              pageSizeOptions={[5]}
              disableSelectionOnClick
              components={{
                NoRowsOverlay: () => (
                  <Stack height="100%" alignItems="center" justifyContent="center">
                    No open positions
                  </Stack>
                ),
              }}
              sx={{
                '& .MuiDataGrid-cell': { borderColor: theme.palette.divider },
                '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider }
              }}
            />
          </Box>
        </Paper>
      </Stack>

      {/* Completed Trades Table */}
      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Completed Trades 
          {completedTrades && completedTrades.length > 0 && (
            <Chip label={`${completedTrades.length} trades`} size="small" sx={{ ml: 2 }} />
          )}
        </Typography>
        <Box sx={{ height: 400, width: '100%' }}>
          <DataGrid 
            rows={completedTrades || []} 
            columns={tradeColumns} 
            pageSize={5} 
            rowsPerPageOptions={[5, 10, 25]} 
            disableSelectionOnClick 
            sx={{ 
              '& .MuiDataGrid-cell': { borderColor: theme.palette.divider }, 
              '& .MuiDataGrid-columnHeaders': { backgroundColor: theme.palette.background.default, borderColor: theme.palette.divider } 
            }} 
          />
        </Box>
      </Paper>
    </Container>
  );
};

export default PaperTradingPage;