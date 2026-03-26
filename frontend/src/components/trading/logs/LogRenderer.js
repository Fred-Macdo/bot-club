import React from 'react';
import { Box, Typography, useTheme, Chip } from '@mui/material';
import DefaultLog from './DefaultLog';
import PositionsLog from './PositionsLog';
import AccountValueLog from './AccountValueLog';
import PriceDataframeLog from './PriceDataframeLog';
import ExitConditionsLog from './ExitConditionsLog';
import PortfolioSnapshotLog from './PortfolioSnapshotLog';

const LogRenderer = ({ log, index }) => {
  const theme = useTheme();

  // If no event_type, or event_type is 'log', render default
  if (!log.event_type || log.event_type === 'log') {
    return <DefaultLog log={log} />;
  }

  switch (log.event_type) {
    case 'positions':
      return <PositionsLog log={log} />;
    case 'account_value':
      return <AccountValueLog log={log} />;
    case 'price_dataframe':
      return <PriceDataframeLog log={log} />;
    case 'exit_conditions':
      return <ExitConditionsLog log={log} />;
    case 'portfolio_snapshot':
      return <PortfolioSnapshotLog log={log} />;
    default:
      return <DefaultLog log={log} />;
  }
};

export default LogRenderer;
