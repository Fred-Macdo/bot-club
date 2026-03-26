import React from 'react';
import { Box, Typography, useTheme, Chip, Alert } from '@mui/material';
import ExitToAppIcon from '@mui/icons-material/ExitToApp';

const ExitConditionsLog = ({ log }) => {
  const theme = useTheme();
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1, p: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
        <Typography component="span" variant="caption" sx={{ color: theme.palette.text.secondary, mr: 1 }}>
          {timestamp}
        </Typography>
        <Chip 
          icon={<ExitToAppIcon sx={{ fontSize: 14 }} />} 
          label="Exit Signal" 
          size="small" 
          color="warning" 
          variant="filled" 
          sx={{ height: 20, fontSize: '0.7rem' }}
        />
      </Box>
      <Alert severity="warning" variant="outlined" sx={{ py: 0, px: 2 }}>
        <Typography variant="body2" sx={{ fontWeight: 500 }}>
          {log.message}
        </Typography>
      </Alert>
    </Box>
  );
};

export default ExitConditionsLog;
