import React from 'react';
import { Box, Typography, useTheme } from '@mui/material';

const DefaultLog = ({ log }) => {
  const theme = useTheme();
  
  // Format timestamp
  const timestamp = log.timestamp 
    ? new Date(log.timestamp).toLocaleTimeString()
    : new Date().toLocaleTimeString();

  const levelColor = log.level === 'WARNING' || log.level === 'ERROR' 
    ? theme.palette.warning.main 
    : theme.palette.info.main;

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1 }}>
      <Typography component="span" variant="body2" sx={{ color: theme.palette.text.secondary }}>
        {timestamp}
      </Typography>
      <Typography component="span" variant="body2" sx={{ color: levelColor, mx: 1, fontWeight: 'bold' }}>
        [{log.level}]
      </Typography>
      <Typography component="span" variant="body2" sx={{ fontFamily: 'monospace' }}>
        {log.message}
      </Typography>
    </Box>
  );
};

export default DefaultLog;
