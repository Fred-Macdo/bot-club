import React from 'react';
import { Box, Typography, useTheme, Chip } from '@mui/material';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';

const PositionsLog = ({ log }) => {
  const theme = useTheme();
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1, backgroundColor: 'rgba(25, 118, 210, 0.04)', p: 1, borderRadius: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
        <Typography component="span" variant="caption" sx={{ color: theme.palette.text.secondary, mr: 1 }}>
          {timestamp}
        </Typography>
        <Chip 
          icon={<LocalOfferIcon sx={{ fontSize: 14 }} />} 
          label="Positions" 
          size="small" 
          color="primary" 
          variant="outlined" 
          sx={{ height: 20, fontSize: '0.7rem' }}
        />
      </Box>
      <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
        {log.message.replace('Current Positions:', '').trim() || 'No active positions'}
      </Typography>
    </Box>
  );
};

export default PositionsLog;
