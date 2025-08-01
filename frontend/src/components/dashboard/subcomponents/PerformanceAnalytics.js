import React from 'react';
import { Paper, Typography, Box, Grid, useTheme } from '@mui/material';

const PerformanceAnalytics = ({ stats }) => {
  const theme = useTheme();

  return (
    <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Performance Analytics
      </Typography>
      <Box sx={{ mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Overall Trade Statistics
        </Typography>
        <Grid container spacing={1}>
          <Grid item xs={6} sm={4}><Typography variant="body2">Total Trades:</Typography></Grid>
          <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{stats?.totalTrades}</Typography></Grid>
          <Grid item xs={6} sm={4}><Typography variant="body2">Winning Trades:</Typography></Grid>
          <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>{stats?.winningTrades} ({stats?.winRate?.toFixed(1)}%)</Typography></Grid>
          <Grid item xs={6} sm={4}><Typography variant="body2">Losing Trades:</Typography></Grid>
          <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{stats?.losingTrades} ({(100 - (stats?.winRate || 0))?.toFixed(1)}%)</Typography></Grid>
          <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Win (%):</Typography></Grid>
          <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>N/A</Typography></Grid>
          <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Loss (%):</Typography></Grid>
          <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>N/A</Typography></Grid>
        </Grid>
      </Box>
    </Paper>
  );
};

export default PerformanceAnalytics;
