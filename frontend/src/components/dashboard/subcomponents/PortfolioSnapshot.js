import React from 'react';
import { Paper, Typography, Box } from '@mui/material';

const PortfolioSnapshot = ({ stats }) => {
  return (
    <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Portfolio Snapshot
      </Typography>
      <Box sx={{
        p: 2, borderRadius: 1,
        bgcolor: stats?.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.1)' : 'rgba(211, 47, 47, 0.1)',
        border: 1, borderColor: stats?.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.3)' : 'rgba(211, 47, 47, 0.3)'
      }}>
        <Typography variant="body2" sx={{ mb: 1 }}><strong>Initial Portfolio Value (approx.):</strong> ${stats?.initialCapital?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
        <Typography variant="body2" sx={{ mb: 1 }}><strong>Current Portfolio Value:</strong> ${stats?.finalEquity?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
        <Typography variant="body2" sx={{ mb: 1 }}><strong>Absolute Gain/Loss:</strong> ${(stats?.finalEquity - stats?.initialCapital)?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
        <Typography variant="body2" sx={{ fontWeight: 'bold' }}><strong>Total Return:</strong> {stats?.totalReturn >= 0 ? '+' : ''}{stats?.totalReturn?.toFixed(2)}%</Typography>
      </Box>
    </Paper>
  );
};

export default PortfolioSnapshot;
