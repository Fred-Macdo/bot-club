import React, { useMemo } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  CircularProgress,
  useTheme
} from '@mui/material';
import Plot from 'react-plotly.js';
import { useDeployedStrategy } from '../../../context/DeployedStrategyContext';

const AccountPerformance = () => {
  const theme = useTheme();
  
  const {
    isDeployed,
    metrics,
    portfolioHistory
  } = useDeployedStrategy();

  const pnlDataPoints = useMemo(() => {
    if (portfolioHistory && portfolioHistory.length > 0) {
      return portfolioHistory.map(p => ({
        timestamp: p.timestamp ? new Date(p.timestamp) : new Date(),
        value: p.total_value || ((p.unrealized_pnl || 0) + (p.realized_pnl || 0))
      }));
    }
    return [];
  }, [portfolioHistory]);

  const currentPnL = pnlDataPoints.length > 0 ? pnlDataPoints[pnlDataPoints.length - 1].value : 0;

  const pnlPlotData = [{
    x: pnlDataPoints.map(d => d.timestamp),
    y: pnlDataPoints.map(d => d.value),
    type: 'scatter',
    mode: 'lines',
    name: 'P&L',
    line: {
      color: currentPnL >= 0 ? theme.palette.success.main : theme.palette.error.main,
      width: 2
    }
  }];

  const pnlPlotLayout = {
    title: 'Strategy Equity',
    xaxis: { title: 'Time' },
    yaxis: { title: 'P&L ($)', tickformat: '$,.0f' },
    plot_bgcolor: theme.palette.background.paper,
    paper_bgcolor: theme.palette.background.paper,
    font: { color: theme.palette.text.primary },
    margin: { l: 60, r: 30, b: 50, t: 50 }
  };

  return (
    <>
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

      {/* Strategy Equity Chart */}
      <Paper sx={{ p: 2, height: 400 }}>
        <Typography variant="h6" gutterBottom>Strategy Equity</Typography>
        {isDeployed && pnlDataPoints.length > 0 ? (
          <Plot 
            data={pnlPlotData} 
            layout={pnlPlotLayout} 
            style={{ width: '100%', height: '320px' }} 
            config={{ responsive: true, displaylogo: false }}
          />
        ) : isDeployed ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '320px', color: theme.palette.text.secondary }}>
            <CircularProgress size={24} sx={{ mb: 2 }} />
            <Typography>Waiting for portfolio data...</Typography>
            <Typography variant="caption">Data will appear after the first trading iteration</Typography>
          </Box>
        ) : (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '320px', color: theme.palette.text.secondary }}>
            Deploy a strategy to see trading performance
          </Box>
        )}
      </Paper>
    </>
  );
};

export default AccountPerformance;
