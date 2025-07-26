import React from 'react';
import {
  Container,
  Typography,
  Box,
  Paper,
  Grid,
  Card,
  CardContent,
  Button,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Alert,
  Chip,
  Divider,
  Link as MuiLink,  // Alias the Material-UI Link
} from '@mui/material';
import {
  AccountBalance as BrokerageIcon,
  DataUsage as DataIcon,
  TrendingUp as TradingIcon,
  TrendingUp as TrendingUpIcon,     // For entry conditions
  TrendingDown as TrendingDownIcon, // For exit conditions
  Build as BuildIcon,
  PlayArrow as PlayIcon,
  CheckCircle as CheckIcon,
  Launch as LaunchIcon,
  Assessment as AnalyticsIcon,
  Security as SecurityIcon,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import { Link as RouterLink } from 'react-router-dom';  // Alias the React Router Link

const GettingStarted = () => {
  const steps = [
    {
      label: 'Set Up Your Brokerage Account',
      description: 'Connect with Alpaca for live trading',
      icon: <BrokerageIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            Trading on our platform is powered by <MuiLink href="https://alpaca.markets/">Alpaca</MuiLink>
            , a commission-free brokerage. 
            You'll need to create an Alpaca account to execute live trades.
          </Typography>
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="body2">
              Alpaca offers both Paper Trading (practice) and Live Trading accounts. 
              We recommend starting with Paper Trading to test your strategies risk-free.
            </Typography>
          </Alert>
          <List dense>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Sign up at alpaca.markets" 
                secondary="Create your free account and complete verification"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Generate API Keys" 
                secondary="Create API keys for both Paper and Live trading"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Fund Your Account" 
                secondary="Add funds to your live account when ready (Paper trading uses virtual money)"
              />
            </ListItem>
          </List>
          <Button 
            variant="outlined" 
            startIcon={<LaunchIcon />}
            href="https://alpaca.markets" 
            target="_blank"
            sx={{ mt: 2 }}
          >
            Sign Up for Alpaca
          </Button>
        </Box>
      )
    },
    {
      label: 'Configure API Credentials',
      description: 'Connect your accounts to our platform',
      icon: <SecurityIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            Once you have your Alpaca API keys, configure them in your account settings. 
            This allows our platform to execute trades on your behalf.
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Navigate to Account Settings" 
                secondary="Go to the Account page and find API Configuration"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Add Paper Trading Keys" 
                secondary="Start with paper trading to test strategies safely"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Test Connection" 
                secondary="Verify your API keys work correctly"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Add Live Trading Keys (Optional)" 
                secondary="When ready for live trading, add your live API credentials"
              />
            </ListItem>
          </List>
          <Button 
            component={RouterLink} 
            to="/account" 
            variant="contained" 
            sx={{ mt: 2 }}
          >
            Configure API Keys
          </Button>
        </Box>
      )
    },
    {
      label: 'Set Up Data Provider (Optional)',
      description: 'Enhanced market data with Polygon.io',
      icon: <DataIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            For enhanced backtesting with high-quality market data, we support <MuiLink href="https://polygon.io/">Polygon.io</MuiLink> 
            as an alternative data provider. This is optional but recommended for better backtesting accuracy.
          </Typography>
          <Alert severity="success" sx={{ mb: 2 }}>
            <Typography variant="body2">
              Polygon.io offers a free tier that's perfect for getting started with backtesting!
            </Typography>
          </Alert>
          <List dense>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Create Free Polygon Account" 
                secondary="Sign up at polygon.io for free market data access"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Get API Key" 
                secondary="Generate your API key from the Polygon dashboard"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Configure in Settings" 
                secondary="Add your Polygon API key to enhance backtesting data"
              />
            </ListItem>
          </List>
          <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
            <Button 
              variant="outlined" 
              startIcon={<LaunchIcon />}
              href="https://polygon.io" 
              target="_blank"
            >
              Sign Up for Polygon.io
            </Button>
            <Button 
              component={RouterLink} 
              to="/account" 
              variant="outlined"
            >
              Configure Polygon API
            </Button>
          </Box>
        </Box>
      )
    },
    {
      label: 'Build Your First Strategy',
      description: 'Create automated trading strategies',
      icon: <BuildIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            Our platform allows you to create automated trading strategies using common technical indicators. 
            You can define entry and exit conditions based on various market signals.
          </Typography>
          
          <Typography variant="h6" gutterBottom sx={{ mt: 3, mb: 2 }}>
            Available Technical Indicators:
          </Typography>
          
          {/* Moving Averages */}
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2, mb: 1 }}>
            Moving Averages
          </Typography>
          <Box sx={{ mb: 3, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Indicator</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Description</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Parameters</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/s/sma.asp" target="_blank" rel="noopener">
                      <strong>SMA</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Simple Moving Average</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Number of periods to average (default: 20)</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/e/ema.asp" target="_blank" rel="noopener">
                      <strong>EMA</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Exponential Moving Average</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Number of periods with exponential weighting (default: 20)</td>
                </tr>
              </tbody>
            </table>
          </Box>

          {/* Oscillators */}
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2, mb: 1 }}>
            Oscillators
          </Typography>
          <Box sx={{ mb: 3, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Indicator</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Description</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Parameters</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/r/rsi.asp" target="_blank" rel="noopener">
                      <strong>RSI</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Relative Strength Index</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 14)</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/investing/timing-trades-with-commodity-channel-index/" target="_blank" rel="noopener">
                      <strong>CCI</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Commodity Channel Index</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 20)</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/m/mfi.asp" target="_blank" rel="noopener">
                      <strong>MFI</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Money Flow Index</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 14)</td>
                </tr>
              </tbody>
            </table>
          </Box>

          {/* Volatility Indicators */}
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2, mb: 1 }}>
            Volatility Indicators
          </Typography>
          <Box sx={{ mb: 3, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Indicator</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Description</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Parameters</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/a/atr.asp" target="_blank" rel="noopener">
                      <strong>ATR</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Average True Range</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 14)</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/b/bollingerbands.asp" target="_blank" rel="noopener">
                      <strong>BBANDS</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Bollinger Bands</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    period: MA period (default: 20)<br />
                    std_dev: Standard deviation multiplier (default: 2)
                  </td>
                </tr>
              </tbody>
            </table>
          </Box>

          {/* Trend Indicators */}
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2, mb: 1 }}>
            Trend Indicators
          </Typography>
          <Box sx={{ mb: 3, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Indicator</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Description</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Parameters</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/articles/trading/07/adx-trend-indicator.asp" target="_blank" rel="noopener">
                      <strong>ADX</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Average Directional Index</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 14)</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/m/macd.asp" target="_blank" rel="noopener">
                      <strong>MACD</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Moving Average Convergence Divergence</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    fast_period: Fast EMA period (default: 12)<br />
                    slow_period: Slow EMA period (default: 26)<br />
                    signal_period: Signal line period (default: 9)
                  </td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/s/stochasticoscillator.asp" target="_blank" rel="noopener">
                      <strong>STOCH</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Stochastic Oscillator</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    k_period: %K period (default: 14)<br />
                    d_period: %D period (default: 3)<br />
                    slowing: Slowing period (default: 3)
                  </td>
                </tr>
              </tbody>
            </table>
          </Box>

          {/* Volume Indicators */}
          <Typography variant="subtitle1" sx={{ fontWeight: 'bold', mt: 2, mb: 1 }}>
            Volume Indicators
          </Typography>
          <Box sx={{ mb: 3, overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
              <thead>
                <tr style={{ backgroundColor: '#f5f5f5' }}>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Indicator</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Description</th>
                  <th style={{ padding: '8px', textAlign: 'left', border: '1px solid #ddd', fontWeight: 'bold' }}>Parameters</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/o/onbalancevolume.asp" target="_blank" rel="noopener">
                      <strong>OBV</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>On-Balance Volume</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>No parameters required</td>
                </tr>
                <tr>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>
                    <MuiLink href="https://www.investopedia.com/terms/v/vwap.asp" target="_blank" rel="noopener">
                      <strong>VWAP</strong>
                    </MuiLink>
                  </td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>Volume-Weighted Average Price</td>
                  <td style={{ padding: '8px', border: '1px solid #ddd' }}>period: Lookback period (default: 5)</td>
                </tr>
              </tbody>
            </table>
          </Box>

          <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
            Strategy Components:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon><TrendingUpIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Entry Conditions" 
                secondary="Define when to enter trades (e.g., RSI < 30 AND price crosses above SMA)"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><TrendingDownIcon color="error" /></ListItemIcon>
              <ListItemText 
                primary="Exit Conditions" 
                secondary="Define when to exit trades (e.g., RSI > 70 OR stop loss triggered)"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><SecurityIcon color="warning" /></ListItemIcon>
              <ListItemText 
                primary="Risk Management" 
                secondary="Set position sizing, stop losses, and take profit levels"
              />
            </ListItem>
          </List>
          <Button 
            component={RouterLink} 
            to="/strategy-builder" 
            variant="contained" 
            startIcon={<BuildIcon />}
            sx={{ mt: 2 }}
          >
            Create Your First Strategy
          </Button>
        </Box>
      )
    },
    {
      label: 'Backtest Your Strategy',
      description: 'Test strategies with historical data',
      icon: <AnalyticsIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            Before risking real money, backtest your strategies using historical market data. 
            This helps you understand how your strategy would have performed in the past.
          </Typography>
          <List dense>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Select Your Strategy" 
                secondary="Choose from your created strategies or use our default examples"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Set Backtest Parameters" 
                secondary="Choose date range, initial capital, and timeframe"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Analyze Results" 
                secondary="Review performance metrics, equity curve, and individual trades"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Refine Strategy" 
                secondary="Adjust parameters and re-test until satisfied"
              />
            </ListItem>
          </List>
          <Button 
            component={RouterLink} 
            to="/backtest" 
            variant="contained" 
            startIcon={<AnalyticsIcon />}
            sx={{ mt: 2 }}
          >
            Start Backtesting
          </Button>
        </Box>
      )
    },
    {
      label: 'Deploy and Monitor',
      description: 'Go live with your strategies',
      icon: <PlayIcon />,
      content: (
        <Box>
          <Typography variant="body1" paragraph>
            Once you're satisfied with your backtest results, you can deploy your strategy 
            for live trading. Start with paper trading to gain confidence before using real money.
          </Typography>
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Typography variant="body2">
              <strong>Important:</strong> Always start with paper trading to verify your strategy 
              works as expected in live market conditions before deploying with real money.
            </Typography>
          </Alert>
          <List dense>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Paper Trading First" 
                secondary="Test your strategy with virtual money in real market conditions"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Monitor Performance" 
                secondary="Track your strategy's performance on the dashboard"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><CheckIcon color="success" /></ListItemIcon>
              <ListItemText 
                primary="Go Live When Ready" 
                secondary="Deploy to live trading once you're confident in the strategy"
              />
            </ListItem>
          </List>
          <Button 
            component={RouterLink} 
            to="/dashboard" 
            variant="contained" 
            startIcon={<TimelineIcon />}
            sx={{ mt: 2 }}
          >
            View Dashboard
          </Button>
        </Box>
      )
    }
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box sx={{mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom sx={{ fontWeight: 'bold' }}>
          Getting Started
        </Typography>
        <Typography variant="h6" color="text.secondary" sx={{ mb: 3 }}>
          Welcome to Bot Club! Follow these steps to start automating your trading strategies.
        </Typography>
      </Box>

      {/* Introduction Paragraphs */}
      <Paper sx={{ p: 4, mb: 4, bgcolor: 'background.paper' }}>
        <Typography variant="body1" paragraph sx={{ fontSize: '1.1rem', lineHeight: 1.7 }}>
          <strong>Bot Club</strong> is designed to make algorithmic trading accessible to everyone, whether you're a seasoned trader looking to automate your proven strategies or a newcomer eager to learn systematic trading. Our platform bridges the gap between complex trading algorithms and user-friendly design, allowing you to build, test, and deploy sophisticated trading strategies without writing a single line of code.
        </Typography>
        
        <Typography variant="body1" sx={{ fontSize: '1.1rem', lineHeight: 1.7 }}>
          Using popular technical indicators like RSI, MACD, Bollinger Bands, and moving averages, you can create custom entry and exit conditions that execute trades automatically through your <strong>Alpaca brokerage account</strong>. Start with paper trading to test your ideas risk-free, then deploy to live markets when you're confident. With optional <strong>Polygon.io integration</strong> for enhanced market data, comprehensive backtesting tools, and real-time performance monitoring, Bot Club provides everything you need to transform your trading ideas into automated, profitable strategies.
        </Typography>
      </Paper>

      {/* Step-by-Step Guide */}
      <Paper sx={{ p: 3 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
          Step-by-Step Setup Guide
        </Typography>
        
        <Stepper orientation="vertical">
          {steps.map((step, index) => (
            <Step key={step.label} active={true}>
              <StepLabel
                StepIconComponent={() => (
                  <Box sx={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center',
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    bgcolor: 'primary.main',
                    color: 'white'
                  }}>
                    {step.icon}
                  </Box>
                )}
              >
                <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
                  {step.label}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {step.description}
                </Typography>
              </StepLabel>
              <StepContent>
                <Box sx={{ ml: 2, mt: 2, mb: 3 }}>
                  {step.content}
                </Box>
              </StepContent>
            </Step>
          ))}
        </Stepper>
      </Paper>

      {/* Additional Resources */}
      <Box sx={{ mt: 4 }}>
        <Typography variant="h5" gutterBottom>
          Additional Resources
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={3}>
            <Button
              component={RouterLink}
              to="/strategy-builder"
              variant="outlined"
              fullWidth
              startIcon={<BuildIcon />}
            >
              Strategy Builder
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button
              component={RouterLink}
              to="/backtest"
              variant="outlined"
              fullWidth
              startIcon={<AnalyticsIcon />}
            >
              Backtesting
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button
              component={RouterLink}
              to="/account"
              variant="outlined"
              fullWidth
              startIcon={<SecurityIcon />}
            >
              Account Settings
            </Button>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Button
              component={RouterLink}
              to="/dashboard"
              variant="outlined"
              fullWidth
              startIcon={<TimelineIcon />}
            >
              Dashboard
            </Button>
          </Grid>
        </Grid>
      </Box>
    </Container>
  );
};

export default GettingStarted;
