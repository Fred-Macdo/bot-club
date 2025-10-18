import React, { useState, useMemo, useEffect } from 'react';
import PropTypes from 'prop-types';
import {
  Box,
  Collapse,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Paper,
  Chip,
  useTheme,
  TablePagination,
  CircularProgress,
  Alert
} from '@mui/material';
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown';
import KeyboardArrowUpIcon from '@mui/icons-material/KeyboardArrowUp';
import Plot from 'react-plotly.js';
import { backtestApi } from '../../api/Client';

const Row = ({ row, strategy }) => {
  const { backtest } = row;
  const [open, setOpen] = useState(false);
  const theme = useTheme();

  const equityChartData = useMemo(() => {
    // Handle the new equity_curve structure with separate arrays
    if (!backtest.equity_curve || !backtest.equity_curve.timestamps || !backtest.equity_curve.values) {
      return null;
    }

    const { timestamps, values, cash, positions_value } = backtest.equity_curve;

    console.log('Creating chart for backtest ID:', backtest.backtest_id);
    console.log('Equity curve data points:', timestamps.length);

    return {
      data: [
        {
          x: timestamps,
          y: values,
          type: 'scatter',
          mode: 'lines',
          name: 'Total Portfolio Value',
          line: { color: theme.palette.primary.main, width: 2 },
          showlegend: true
        },
        {
          x: timestamps,
          y: cash,
          type: 'scatter',
          mode: 'lines',
          name: 'Cash',
          line: { color: theme.palette.secondary.main, width: 1 },
          showlegend: true
        },
        {
          x: timestamps,
          y: positions_value,
          type: 'scatter',
          mode: 'lines',
          name: 'Positions Value',
          line: { color: theme.palette.success.main, width: 1 },
          showlegend: true
        }
      ],
      layout: {
        title: 'Equity Curve',
        xaxis: { 
          title: 'Date',
          type: 'date'
        },
        yaxis: { 
          title: 'Value ($)',
          tickformat: '$,.0f'
        },
        plot_bgcolor: theme.palette.background.paper,
        paper_bgcolor: theme.palette.background.default,
        font: { color: theme.palette.text.primary },
        legend: {
          x: 0,
          y: 1,
          bgcolor: 'rgba(54, 221, 196, 0)'
        },
        hovermode: 'x unified',
        showlegend: true
      },
      config: {
        displayModeBar: false,
        staticPlot: false,
        responsive: true
      }
    };
  }, [backtest.backtest_id, backtest.equity_curve, theme]);

  // Use metrics from the new data structure
  const metrics = backtest.metrics || {};

  return (
    <React.Fragment>
      <TableRow sx={{ '& > *': { borderBottom: 'unset' } }} onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
        <TableCell>
          <IconButton aria-label="expand row" size="small">
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell>{strategy?.name || backtest.strategy_name || 'N/A'}</TableCell>
        <TableCell>1D</TableCell> {/* Timeframe not in new structure, using default */}
        <TableCell align="right">{metrics.total_return?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{metrics.max_drawdown?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{metrics.win_rate?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{metrics.total_trades ?? 'N/A'}</TableCell>
        <TableCell>{new Date().toLocaleDateString()}</TableCell> {/* Created date not in new structure */}
        <TableCell>2025-01-01</TableCell> {/* Start date not in new structure */}
        <TableCell>2025-05-31</TableCell> {/* End date not in new structure */}
      </TableRow>
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={10}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 1, padding: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
              <Typography variant="h6" gutterBottom component="div">
                Backtest Details
              </Typography>
              
              {/* Performance Metrics Summary */}
              <Box sx={{ mb: 2, p: 2, backgroundColor: theme.palette.background.paper, borderRadius: 1 }}>
                <Typography variant="subtitle1" gutterBottom>Performance Summary</Typography>
                <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 2 }}>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Total Return</Typography>
                    <Typography variant="h6" color={metrics.total_return >= 0 ? 'success.main' : 'error.main'}>
                      {metrics.total_return?.toFixed(2) ?? 'N/A'}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Final Equity</Typography>
                    <Typography variant="h6">
                      ${metrics.final_equity?.toLocaleString() ?? 'N/A'}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Max Drawdown</Typography>
                    <Typography variant="h6" color="error.main">
                      {metrics.max_drawdown?.toFixed(2) ?? 'N/A'}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Win Rate</Typography>
                    <Typography variant="h6">
                      {metrics.win_rate?.toFixed(2) ?? 'N/A'}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Total Trades</Typography>
                    <Typography variant="h6">
                      {metrics.total_trades ?? 'N/A'}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="text.secondary">Profit Factor</Typography>
                    <Typography variant="h6">
                      {metrics.profit_factor?.toFixed(2) ?? 'N/A'}
                    </Typography>
                  </Box>
                </Box>
              </Box>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle1" gutterBottom>Performance Chart</Typography>
                {equityChartData ? (
                  <div key={`plot-container-${backtest.backtest_id}-${open}`}>
                    <Plot 
                      key={`plot-${backtest.backtest_id}-${open}-${Date.now()}`}
                      data={equityChartData.data} 
                      layout={equityChartData.layout} 
                      config={equityChartData.config}
                      style={{ width: '100%', height: '400px' }}
                      useResizeHandler={true}
                      onInitialized={(figure) => {
                        console.log('Plot initialized with data:', figure.data.length, 'traces');
                      }}
                      onUpdate={(figure) => {
                        console.log('Plot updated with data:', figure.data.length, 'traces');
                      }}
                    />
                  </div>
                ) : (
                  <Typography>No equity curve data available.</Typography>
                )}
              </Box>

              <Typography variant="subtitle1" gutterBottom>Trades</Typography>
              <Table size="small" aria-label="trades">
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Side</TableCell>
                    <TableCell>Entry Date</TableCell>
                    <TableCell>Exit Date</TableCell>
                    <TableCell align="right">Entry Price</TableCell>
                    <TableCell align="right">Exit Price</TableCell>
                    <TableCell align="right">Quantity</TableCell>
                    <TableCell align="right">PnL</TableCell>
                    <TableCell align="right">Return %</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {backtest.trades?.map((trade, index) => (
                    <TableRow key={index}>
                      <TableCell>{trade.symbol}</TableCell>
                      <TableCell>
                        <Chip 
                          label={trade.side}
                          color={trade.side === 'long' ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>{new Date(trade.entry_date).toLocaleString()}</TableCell>
                      <TableCell>{trade.exit_date ? new Date(trade.exit_date).toLocaleString() : 'N/A'}</TableCell>
                      <TableCell align="right">${trade.entry_price?.toFixed(2)}</TableCell>
                      <TableCell align="right">${trade.exit_price?.toFixed(2) ?? 'N/A'}</TableCell>
                      <TableCell align="right">{trade.quantity}</TableCell>
                      <TableCell align="right" style={{ color: trade.pnl > 0 ? theme.palette.success.main : theme.palette.error.main }}>
                        ${trade.pnl?.toFixed(2) ?? 'N/A'}
                      </TableCell>
                      <TableCell align="right" style={{ color: trade.return_pct > 0 ? theme.palette.success.main : theme.palette.error.main }}>
                        {trade.return_pct?.toFixed(2) ?? 'N/A'}%
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </React.Fragment>
  );
};

Row.propTypes = {
  row: PropTypes.object.isRequired,
  strategy: PropTypes.object
};

export default function BacktestResults({ strategies = [] }) {
  const [page, setPage] = React.useState(0);
  const [rowsPerPage, setRowsPerPage] = React.useState(5);
  const [backtests, setBacktests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadUserBacktests = async () => {
      try {
        setLoading(true);
        setError(null);
        const fetchedBacktests = await backtestApi.getUserBacktests();
        console.log("fetchedBacktests"); 
        console.log(fetchedBacktests);
        
        // Ensure we have an array and handle the data properly
        if (Array.isArray(fetchedBacktests)) {
          console.log("Number of backtests:", fetchedBacktests.length);
          if (fetchedBacktests.length > 0) {
            console.log("First backtest structure:", fetchedBacktests[0]);
            console.log("First backtest equity_curve:", fetchedBacktests[0]?.equity_curve);
          }
          // Sort by backtest_id since created_at might not be available
          setBacktests(fetchedBacktests.sort((a, b) => b.backtest_id.localeCompare(a.backtest_id)));
        } else {
          console.warn("Expected array but got:", typeof fetchedBacktests, fetchedBacktests);
          setBacktests([]);
        }
      } catch (err) {
        console.error('Error loading user backtests:', err);
        setError('Failed to load backtest history.');
      } finally {
        setLoading(false);
      }
    };
    
    loadUserBacktests();
  }, []);

  const getStrategyById = (id) => strategies.find(s => s.id === id);

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };
  
  if (loading) {
    return (
      <Paper sx={{ p: 2, display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 200 }}>
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>Loading Backtest History...</Typography>
      </Paper>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }
  
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Recent Backtests</Typography>
      <TableContainer>
        <Table aria-label="collapsible table">
          <TableHead>
            <TableRow>
              <TableCell />
              <TableCell>Strategy</TableCell>
              <TableCell>Timeframe</TableCell>
              <TableCell align="right">Return (%)</TableCell>
              <TableCell align="right">Drawdown (%)</TableCell>
              <TableCell align="right">Win Rate (%)</TableCell>
              <TableCell align="right">Trades</TableCell>
              <TableCell>Backtest Date</TableCell>
              <TableCell>Start Date</TableCell>
              <TableCell>End Date</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {backtests.length > 0 ? (
              backtests.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage).map((backtest) => (
                <Row key={backtest.backtest_id} row={{ backtest }} strategy={getStrategyById(backtest.strategy_id)} />
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={10} align="center">
                  No backtest history found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        rowsPerPageOptions={[5, 10, 25]}
        component="div"
        count={backtests.length}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
      />
    </Paper>
  );
}

BacktestResults.propTypes = {
    strategies: PropTypes.array.isRequired,
};
