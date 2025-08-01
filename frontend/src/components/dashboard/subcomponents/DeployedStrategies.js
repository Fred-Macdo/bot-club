import React from 'react';
import { Paper, Typography, Box } from '@mui/material';

const DeployedStrategies = ({ isPaperMode }) => {
  return (
    <Paper sx={{ p: 2, borderRadius: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
      <Box>
        <Typography variant="h6">
          Deployed Strategies
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {isPaperMode ? "Paper Trading Performance" : "Live Trading Performance"}
        </Typography>
      </Box>
    </Paper>
  );
};

export default DeployedStrategies;
