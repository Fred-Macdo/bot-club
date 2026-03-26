import React from 'react';
import { Box, Typography, useTheme, Chip } from '@mui/material';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';

const AccountValueLog = ({ log }) => {
  const theme = useTheme();
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';

  // Parse value from string "Account Value: 12345.67"
  const valueMatch = log.message.match(/Account Value:\s*([\d.]+)/);
  const value = valueMatch ? parseFloat(valueMatch[1]).toFixed(2) : null;

  return (
    <Box sx={{ mb: 1, borderBottom: `1px solid ${theme.palette.divider}`, pb: 1, p: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center' }}>
        <Typography component="span" variant="caption" sx={{ color: theme.palette.text.secondary, mr: 1 }}>
          {timestamp}
        </Typography>
        <Chip 
          icon={<AccountBalanceWalletIcon sx={{ fontSize: 14 }} />} 
          label="Account Value" 
          size="small" 
          color="success" 
          variant="outlined" 
          sx={{ height: 20, fontSize: '0.7rem', mr: 1 }}
        />
         <Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
           {value ? `$${value}` : log.message}
         </Typography>
      </Box>
    </Box>
  );
};

export default AccountValueLog;
