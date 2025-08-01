import React from 'react';
import { Paper, Typography, Box, useTheme } from '@mui/material';
import Plot from 'react-plotly.js';

const AccountPerformanceChart = ({ plotData, plotLayout }) => {
  const theme = useTheme();

  return (
    <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Account Performance
      </Typography>
      <Box sx={{ width: '100%', height: 400 }}>
        <Plot
          data={plotData}
          layout={plotLayout}
          style={{ width: '100%', height: '100%' }}
          useResizeHandler={true}
          config={{ responsive: true, displaylogo: false }}
        />
      </Box>
    </Paper>
  );
};

export default AccountPerformanceChart;
