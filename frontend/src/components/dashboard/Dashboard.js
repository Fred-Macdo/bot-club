import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Paper,
  Button,
  useTheme,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Card,
  CardContent,
  Divider,
} from '@mui/material';
import {
  ZoomIn as ZoomInIcon,
  MonetizationOn as MonetizationOnIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Assessment as AssessmentIcon,
} from '@mui/icons-material';
import Plot from 'react-plotly.js';
import { userConfigApi } from '../../api/Client';


const EquityCurveDashboard = () => {
  const theme = useTheme();

  const [accountEquityData, setAccountEquityData] = useState([]);
  const [accountPlotData, setAccountPlotData] = useState([]);
  const [accountPlotLayout, setAccountPlotLayout] = useState({});
  const [dashboardStats, setDashboardStats] = useState(null);
  const [dashboardTrades, setDashboardTrades] = useState([]);

  useEffect(() => {
    const generateMockEquity = (initialValue = 10000, days = 180, trendFactor = 0.6) => {
      const data = [];
      let currentValue = initialValue;
      const now = new Date();
      for (let i = days; i >= 0; i--) {
        const date = new Date(now);
        date.setDate(date.getDate() - i);
        if (date.getDay() === 0 || date.getDay() === 6) continue;
        const dailyChange = (Math.random() > trendFactor ? -1 : 1) * (Math.random() * 0.02);
        currentValue *= (1 + dailyChange);
        data.push({ date, value: currentValue });
      }
      return data;
    };

    const equityData = generateMockEquity(100000, 252);
    setAccountEquityData(equityData);

    const generateDashboardData = (equityHistory) => {
      if (!equityHistory || equityHistory.length === 0) {
        return { stats: {}, trades: [] };
      }
      const initialCapital = equityHistory[0].value;
      const finalEquity = equityHistory[equityHistory.length - 1].value;
      const totalReturn = ((finalEquity - initialCapital) / initialCapital) * 100;

      const trades = [];
      for (let i = 0; i < 25; i++) {
        const entryDayIndex = Math.floor(Math.random() * (equityHistory.length - 10));
        const exitDayIndex = entryDayIndex + Math.floor(Math.random() * 5) + 5;
        const entryDate = equityHistory[entryDayIndex].date;
        const exitDate = equityHistory[exitDayIndex].date;
        const entryPrice = equityHistory[entryDayIndex].value * (0.05 + Math.random() * 0.1);
        const shares = Math.floor((initialCapital * 0.01) / entryPrice) || 1;
        const side = Math.random() > 0.5 ? 'long' : 'short';
        const exitPrice = entryPrice * (1 + (Math.random() - 0.5) * 0.1);
        const pnl = (side === 'long' ? exitPrice - entryPrice : entryPrice - exitPrice) * shares;
        trades.push({
          id: `trade-${i}`,
          symbol: ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'GOOG'][Math.floor(Math.random() * 5)],
          side,
          entryDate,
          entryPrice,
          exitDate,
          exitPrice,
          shares,
          pnl,
          returnPct: (pnl / (entryPrice * shares)) * 100,
        });
      }
      trades.sort((a, b) => b.exitDate - a.exitDate);

      const winningTrades = trades.filter(t => t.pnl > 0).length;
      const winRate = trades.length > 0 ? (winningTrades / trades.length) * 100 : 0;

      let peak = initialCapital;
      let maxDrawdown = 0;
      equityHistory.forEach(point => {
        if (point.value > peak) peak = point.value;
        const drawdown = ((peak - point.value) / peak) * 100;
        if (drawdown > maxDrawdown) maxDrawdown = drawdown;
      });

      const avgWin = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.returnPct, 0) / (winningTrades || 1);
      const avgLoss = trades.filter(t => t.pnl <= 0).reduce((sum, t) => sum + t.returnPct, 0) / ((trades.length - winningTrades) || 1);

      setDashboardStats({
        initialCapital,
        finalEquity,
        totalReturn,
        totalTrades: trades.length,
        winningTrades,
        losingTrades: trades.length - winningTrades,
        winRate,
        avgWin: avgWin || 0,
        avgLoss: avgLoss || 0,
        maxDrawdown,
        sharpeRatio: Math.random() * 2 + 0.5,
        profitFactor: Math.abs(trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) / (trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0) || -1)),
      });
      setDashboardTrades(trades);
    };

    generateDashboardData(equityData);
  }, []);

  useEffect(() => {
    if (accountEquityData.length > 0) {
      const equityTrace = {
        x: accountEquityData.map(d => d.date),
        y: accountEquityData.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        name: 'Account Equity',
        line: { color: theme.palette.primary.main, width: 2 }
      };

      setAccountPlotData([equityTrace]);
      setAccountPlotLayout({
        autosize: true,
        margin: { l: 70, r: 30, b: 50, t: 50, pad: 4 },
        xaxis: {
          title: 'Date',
          gridcolor: theme.palette.divider,
          linecolor: theme.palette.text.primary,
          tickfont: { color: theme.palette.text.secondary }
        },
        yaxis: {
          title: 'Portfolio Value ($)',
          gridcolor: theme.palette.divider,
          linecolor: theme.palette.text.secondary,
          tickfont: { color: theme.palette.text.secondary },
          tickformat: '$,.0f'
        },
        legend: {
          orientation: 'h',
          yanchor: 'bottom',
          y: 1.02,
          xanchor: 'right',
          x: 1,
          font: { color: theme.palette.text.secondary }
        },
        plot_bgcolor: theme.palette.background.paper,
        paper_bgcolor: theme.palette.background.paper,
        font: { color: theme.palette.text.primary },
        hovermode: 'closest'
      });
    }
  }, [accountEquityData, theme.palette]);

  if (!dashboardStats || dashboardTrades.length === 0) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <Typography>Loading Dashboard Data...</Typography>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Grid container spacing={3}>
        <Grid item xs={12} md={8}>
          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Account Performance
            </Typography>
            <Box sx={{ width: '100%', height: 400 }}>
              <Plot
                data={accountPlotData}
                layout={accountPlotLayout}
                style={{ width: '100%', height: '100%' }}
                useResizeHandler={true}
                config={{ responsive: true, displaylogo: false }}
              />
            </Box>
          </Paper>

          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Performance Analytics
            </Typography>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Overall Trade Statistics
              </Typography>
              <Grid container spacing={1}>
                <Grid item xs={6} sm={4}><Typography variant="body2">Total Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats.totalTrades}</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Winning Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>{dashboardStats.winningTrades} ({dashboardStats.winRate?.toFixed(1)}%)</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Losing Trades:</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{dashboardStats.losingTrades} ({(100 - (dashboardStats.winRate || 0))?.toFixed(1)}%)</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Win (%):</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>{dashboardStats.avgWin?.toFixed(2)}%</Typography></Grid>
                <Grid item xs={6} sm={4}><Typography variant="body2">Avg. Loss (%):</Typography></Grid>
                <Grid item xs={6} sm={8}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{dashboardStats.avgLoss?.toFixed(2)}%</Typography></Grid>
              </Grid>
            </Box>
          </Paper>

          <Paper sx={{ p: 3, borderRadius: 2 }}>
            <Typography variant="h6" gutterBottom>
              Recent Account Activity
            </Typography>
            <TableContainer sx={{ maxHeight: 400 }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Side</TableCell>
                    <TableCell>Entry Date</TableCell>
                    <TableCell>Entry Price</TableCell>
                    <TableCell>Exit Date</TableCell>
                    <TableCell>Exit Price</TableCell>
                    <TableCell>Shares</TableCell>
                    <TableCell>P&L ($)</TableCell>
                    <TableCell>Return (%)</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {dashboardTrades.slice(0, 50).map((trade) => (
                    <TableRow
                      key={trade.id}
                      sx={{
                        '&:nth-of-type(odd)': { bgcolor: theme.palette.action.hover },
                        bgcolor: trade.pnl > 0 ? 'rgba(46, 125, 50, 0.04)' : 'rgba(211, 47, 47, 0.04)'
                      }}
                    >
                      <TableCell>
                        <Chip label={trade.symbol} size="small" sx={{ bgcolor: theme.palette.primary.light, color: theme.palette.primary.contrastText, fontSize: '0.75rem', height: 20 }} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: trade.side === 'long' ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                          {trade.side.toUpperCase()}
                        </Typography>
                      </TableCell>
                      <TableCell>{trade.entryDate.toLocaleDateString()}</TableCell>
                      <TableCell>${trade.entryPrice.toFixed(2)}</TableCell>
                      <TableCell>{trade.exitDate.toLocaleDateString()}</TableCell>
                      <TableCell>${trade.exitPrice.toFixed(2)}</TableCell>
                      <TableCell>{trade.shares}</TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: trade.pnl > 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                          {trade.pnl > 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: trade.returnPct > 0 ? theme.palette.success.main : theme.palette.error.main, fontWeight: 'bold' }}>
                          {trade.returnPct > 0 ? '+' : ''}{trade.returnPct.toFixed(2)}%
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        <Grid item xs={12} md={4}>
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <MonetizationOnIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Total Return</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: dashboardStats.totalReturn >= 0 ? theme.palette.success.main : theme.palette.error.main }}>
                    {dashboardStats.totalReturn >= 0 ? '+' : ''}{dashboardStats.totalReturn?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    ${dashboardStats.initialCapital?.toFixed(2)} → ${dashboardStats.finalEquity?.toFixed(2)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingUpIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Win Rate</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                    {dashboardStats.winRate?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {dashboardStats.winningTrades} / {dashboardStats.totalTrades} trades
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <TrendingDownIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Max Drawdown</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                    -{dashboardStats.maxDrawdown?.toFixed(2)}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Profit Factor: {dashboardStats.profitFactor?.toFixed(2)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={12}>
              <Card>
                <CardContent sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <AssessmentIcon sx={{ color: theme.palette.primary.main, mr: 1 }} />
                    <Typography variant="subtitle2">Sharpe Ratio</Typography>
                  </Box>
                  <Typography variant="h5" sx={{ fontWeight: 'bold' }}>
                    {dashboardStats.sharpeRatio?.toFixed(2)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Avg Win: {dashboardStats.avgWin?.toFixed(2)}% | Avg Loss: {dashboardStats.avgLoss?.toFixed(2)}%
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Paper sx={{ p: 2, borderRadius: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Box>
              <Typography variant="h6">
                Account Overview
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Live Trading Performance
              </Typography>
            </Box>
          </Paper>

          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>
              Portfolio Snapshot
            </Typography>
            <Box sx={{
              p: 2, borderRadius: 1,
              bgcolor: dashboardStats.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.1)' : 'rgba(211, 47, 47, 0.1)',
              border: 1, borderColor: dashboardStats.totalReturn >= 0 ? 'rgba(46, 125, 50, 0.3)' : 'rgba(211, 47, 47, 0.3)'
            }}>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Initial Portfolio Value (approx.):</strong> ${dashboardStats.initialCapital?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Current Portfolio Value:</strong> ${dashboardStats.finalEquity?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ mb: 1 }}><strong>Absolute Gain/Loss:</strong> ${(dashboardStats.finalEquity - dashboardStats.initialCapital)?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</Typography>
              <Typography variant="body2" sx={{ fontWeight: 'bold' }}><strong>Total Return:</strong> {dashboardStats.totalReturn >= 0 ? '+' : ''}{dashboardStats.totalReturn?.toFixed(2)}%</Typography>
            </Box>
          </Paper>

          <Paper sx={{ p: 3, borderRadius: 2, mb: 3 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
              Key Risk Metrics
            </Typography>
            <Grid container spacing={1}>
              <Grid item xs={6}><Typography variant="body2">Max Drawdown:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>{dashboardStats.maxDrawdown?.toFixed(2)}%</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Sharpe Ratio:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats.sharpeRatio?.toFixed(2)}</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Profit Factor:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats.profitFactor?.toFixed(2)}</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2">Win Rate:</Typography></Grid>
              <Grid item xs={6}><Typography variant="body2" sx={{ fontWeight: 'bold' }}>{dashboardStats.winRate?.toFixed(1)}%</Typography></Grid>
            </Grid>
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default EquityCurveDashboard;