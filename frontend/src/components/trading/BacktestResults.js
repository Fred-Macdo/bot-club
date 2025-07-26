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
    if (!backtest.equity_curve?.length) return null;

    const portfolioByTimestamp = backtest.equity_curve.reduce((acc, point) => {
      const { timestamp, value } = point;
      if (!acc[timestamp]) {
        acc[timestamp] = { sum: 0, count: 0 };
      }
      acc[timestamp].sum += value;
      acc[timestamp].count += 1;
      return acc;
    }, {});

    const aggregatedTimestamps = Object.keys(portfolioByTimestamp).sort();
    const aggregatedPortfolioValue = aggregatedTimestamps.map(ts => {
      const data = portfolioByTimestamp[ts];
      return data.sum / data.count;
    });

    console.log('Creating chart for backtest ID:', backtest.id);
    console.log('Equity curve length:', backtest.equity_curve.length);
    console.log('Data arrays length - timestamps:', aggregatedTimestamps.length, 'portfolioValue:', aggregatedPortfolioValue.length);

    return {
      data: [
        {
          x: aggregatedTimestamps,
          y: aggregatedPortfolioValue,
          type: 'scatter',
          mode: 'lines',
          name: 'Total Portfolio Value',
          line: { color: theme.palette.primary.main, width: 2 },
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
  }, [backtest.id, backtest.equity_curve, theme]);

  const performance = backtest.performance || {};

  return (
    <React.Fragment>
      <TableRow sx={{ '& > *': { borderBottom: 'unset' } }} onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
        <TableCell>
          <IconButton aria-label="expand row" size="small">
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell>{strategy?.name || 'N/A'}</TableCell>
        <TableCell align="right">{performance.total_return?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{performance.sharpe_ratio?.toFixed(2) ?? 'N/A'}</TableCell>
        <TableCell align="right">{performance.max_drawdown?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{performance.win_rate?.toFixed(2) ?? 'N/A'}%</TableCell>
        <TableCell align="right">{performance.total_trades ?? 'N/A'}</TableCell>
        <TableCell>{new Date(backtest.created_at).toLocaleDateString()}</TableCell>
      </TableRow>
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={8}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 1, padding: 2, backgroundColor: theme.palette.background.default, borderRadius: 1 }}>
              <Typography variant="h6" gutterBottom component="div">
                Backtest Details
              </Typography>
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle1" gutterBottom>Performance Chart</Typography>
                {/* Temporary debug button */}
                <button onClick={() => console.log('Backtest data:', backtest)}>
                  Debug: Log Backtest Data
                </button>
                {equityChartData ? (
                  <div key={`plot-container-${backtest.id}-${open}`}>
                    <Plot 
                      key={`plot-${backtest.id}-${open}-${Date.now()}`}
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
                        {trade.pnl?.toFixed(2) ?? 'N/A'}
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
        console.log("Number of backtests:", fetchedBacktests.length);
        console.log("First backtest equity_curve:", fetchedBacktests[0]?.equity_curve?.slice(0, 3));
        setBacktests(fetchedBacktests.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)));
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
              <TableCell>Date</TableCell>
              <TableCell>Start Date</TableCell>
              <TableCell>End Date</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {backtests.length > 0 ? (
              backtests.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage).map((backtest) => (
                <Row key={backtest.id} row={{ backtest }} strategy={getStrategyById(backtest.strategy_id)} />
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={8} align="center">
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
