import React from 'react';
import { Box, Typography, useTheme, Chip } from '@mui/material';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';

const parsePositionsData = (log) => {
  if (log.data?.positions) return log.data;
  if (typeof log.message === 'string') {
    try { return JSON.parse(log.message); } catch { /* ignore */ }
  }
  return null;
};

const PositionsLog = ({ log }) => {
  const theme = useTheme();
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';
  const parsed = parsePositionsData(log);
  const positions = parsed?.positions || [];
  const title = parsed?.title || `Current Positions (${positions.length} open)`;

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
        <Typography component="span" variant="caption" sx={{ ml: 1, color: theme.palette.text.secondary }}>
          {title}
        </Typography>
      </Box>
      {positions.length === 0 ? (
        <Typography variant="body2" sx={{ color: theme.palette.text.secondary, fontStyle: 'italic' }}>
          No active positions
        </Typography>
      ) : (
        positions.map((pos, i) => (
          <Box key={pos.lot_id || i} sx={{ display: 'flex', gap: 2, ml: 1, mt: 0.5 }}>
            <Typography variant="body2" sx={{ fontWeight: 'bold', minWidth: 60 }}>
              {pos.symbol}
            </Typography>
            <Typography variant="body2">
              {pos.quantity?.toLocaleString(undefined, { maximumFractionDigits: 6 })} units
            </Typography>
            <Typography variant="body2" sx={{ color: theme.palette.text.secondary }}>
              @ ${pos.entry_price?.toFixed(4)}
            </Typography>
          </Box>
        ))
      )}
    </Box>
  );
};

export default PositionsLog;
