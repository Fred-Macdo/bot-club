import React from 'react';
import {
  Box,
  Typography,
  Paper,
  Alert,
  useTheme
} from '@mui/material';
import { useTradingMode } from '../../../context/DeployedStrategyContext';
import LogRenderer from '../logs/LogRenderer';

const TradingLogs = ({ mode = 'paper' }) => {
  const theme = useTheme();
  
  const {
    logs,
    socketError
  } = useTradingMode(mode);

  return (
    <Paper sx={{ p: 2, height: 400, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="h6" gutterBottom>Trading Logs</Typography>
      <Box 
        sx={{ 
          flexGrow: 1, 
          overflow: 'auto', 
          border: `1px solid ${theme.palette.divider}`, 
          borderRadius: 1, 
          p: 1, 
          backgroundColor: theme.palette.background.default 
        }}
      >
        {socketError && <Alert severity="error">{socketError}</Alert>}
        {logs.map((log, index) => (
          <LogRenderer key={index} log={log} index={index} />
        ))}
        {logs.length === 0 && !socketError && (
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: theme.palette.text.secondary }}>
            Waiting for logs...
          </Box>
        )}
      </Box>
    </Paper>
  );
};

export default TradingLogs;
