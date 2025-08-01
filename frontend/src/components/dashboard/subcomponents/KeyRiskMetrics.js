import React from 'react';
import { Paper, Typography, Grid, useTheme } from '@mui/material';

const KeyRiskMetrics = ({ stats }) => {
  const theme = useTheme();

  return (
    <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
        Key Risk Metrics
      </Typography>
      <Grid container spacing={1}>
        <Grid item xs={6}><Typography variant="body2">Max Drawdown:</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{stats?.maxDrawdown?.toFixed(2)}%</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2">Sharpe Ratio:</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{stats?.sharpeRatio}</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2">Profit Factor:</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{stats?.profitFactor}</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2">Win Rate:</Typography></Grid>
        <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{stats?.winRate?.toFixed(1)}%</Typography></Grid>
      </Grid>
    </Paper>
  );
};

export default KeyRiskMetrics;
