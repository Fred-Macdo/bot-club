import React from 'react';
import { Box, Typography, useTheme, Chip } from '@mui/material';
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet';

const parseAccountData = (log) => {
  if (log.data?.account_value != null) return log.data;
  if (typeof log.message === 'string') {
    try { return JSON.parse(log.message); } catch { /* ignore */ }
  }
  return null;
};

const AccountValueLog = ({ log }) => {
  const theme = useTheme();
  const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : '';
  const parsed = parseAccountData(log);
  const accountValue = parsed?.account_value;
  const cash = parsed?.cash;

  const fmtValue = accountValue != null
    ? `$${Number(accountValue).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : null;
  const fmtCash = cash != null
    ? `$${Number(cash).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : null;

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
          {fmtValue || log.message}
        </Typography>
        {fmtCash && (
          <Typography variant="body2" sx={{ ml: 2, color: theme.palette.text.secondary }}>
            Cash: {fmtCash}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default AccountValueLog;
