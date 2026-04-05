import React, { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { getTradingStatus, tradingApi, authApi, userApi, strategyApi } from '../api/Client';
import { getWebSocketUrl } from '../utils/apiConfig';

const DeployedStrategyContext = createContext();

// Default state for a single mode slot
const DEFAULT_MODE_STATE = {
  deployedStrategy: null,
  isDeployed: false,
  dataProvider: 'alpaca',
  deploymentTime: null,
  activeTaskId: null,
  sessionHealth: 'unknown',
  logs: [],
  socketStatus: 'disconnected',
  socketError: null,
  trades: [],
  completedTrades: [],
  positions: [],
  metrics: null,
  portfolio: null,
  portfolioHistory: [],
  indicatorData: {},
  priceDataframes: {},
};

// Backwards-compatible hook (returns raw context)
export const useDeployedStrategy = () => {
  const context = useContext(DeployedStrategyContext);
  if (!context) {
    throw new Error('useDeployedStrategy must be used within a DeployedStrategyProvider');
  }
  return context;
};

// New mode-specific hook
export const useTradingMode = (mode) => {
  const ctx = useDeployedStrategy();
  const ms = ctx.modeStates[mode] || DEFAULT_MODE_STATE;

  return useMemo(() => ({
    deployedStrategy: ms.deployedStrategy,
    isDeployed: ms.isDeployed,
    dataProvider: ms.dataProvider,
    deploymentTime: ms.deploymentTime,
    activeTaskId: ms.activeTaskId,
    sessionHealth: ms.sessionHealth,
    logs: ms.logs,
    socketStatus: ms.socketStatus,
    socketError: ms.socketError,
    trades: ms.trades,
    completedTrades: ms.completedTrades,
    positions: ms.positions,
    metrics: ms.metrics,
    portfolio: ms.portfolio,
    portfolioHistory: ms.portfolioHistory,
    indicatorData: ms.indicatorData,
    priceDataframes: ms.priceDataframes,
    // Mode-aware actions
    setDataProvider: (provider) => ctx.setModeDataProvider(mode, provider),
    setDeploymentState: (strategy, taskId, provider, tradingMode) =>
      ctx.setDeploymentState(strategy, taskId, provider, tradingMode || mode),
    stopStrategy: () => ctx.stopStrategy(mode),
    clearDeployment: () => ctx.clearDeployment(mode),
    deployStrategy: (strategy, provider, tradingMode) =>
      ctx.deployStrategy(strategy, provider, tradingMode || mode),
    mode,
  }), [ms, ctx, mode]);
};

export const DeployedStrategyProvider = ({ children }) => {
  // Hydrate from localStorage
  const getInitialModeStates = () => {
    const states = { paper: { ...DEFAULT_MODE_STATE }, live: { ...DEFAULT_MODE_STATE } };
    try {
      const saved = localStorage.getItem('tradingModeStates');
      if (saved) {
        const parsed = JSON.parse(saved);
        for (const m of ['paper', 'live']) {
          if (parsed[m]) {
            states[m] = {
              ...DEFAULT_MODE_STATE,
              deployedStrategy: parsed[m].strategy || null,
              isDeployed: parsed[m].isDeployed || false,
              dataProvider: parsed[m].dataProvider || 'alpaca',
              deploymentTime: parsed[m].deploymentTime || null,
              activeTaskId: parsed[m].activeTaskId || null,
            };
          }
        }
        return states;
      }
      // Migration: read old single-mode localStorage
      const oldSaved = localStorage.getItem('deployedStrategy');
      if (oldSaved) {
        const parsed = JSON.parse(oldSaved);
        const oldMode = parsed.mode || 'paper';
        states[oldMode] = {
          ...DEFAULT_MODE_STATE,
          deployedStrategy: parsed.strategy || null,
          isDeployed: parsed.isDeployed || false,
          dataProvider: parsed.dataProvider || 'alpaca',
          deploymentTime: parsed.deploymentTime || null,
          activeTaskId: parsed.activeTaskId || null,
        };
        localStorage.removeItem('deployedStrategy');
      }
    } catch (e) {
      console.error('DeployedStrategyContext: Error parsing localStorage:', e);
    }
    return states;
  };

  const [modeStates, setModeStates] = useState(getInitialModeStates);

  // Per-mode WebSocket refs
  const wsRefs = useRef({ paper: null, live: null });
  const lastMessageIdRefs = useRef({ paper: null, live: null });
  const isDeployedRefs = useRef({
    paper: modeStates.paper.isDeployed,
    live: modeStates.live.isDeployed,
  });

  useEffect(() => {
    isDeployedRefs.current.paper = modeStates.paper.isDeployed;
    isDeployedRefs.current.live = modeStates.live.isDeployed;
  }, [modeStates.paper.isDeployed, modeStates.live.isDeployed]);

  // Mode state updater helper
  const updateModeState = useCallback((mode, updates) => {
    setModeStates(prev => ({
      ...prev,
      [mode]: { ...prev[mode], ...updates },
    }));
  }, []);

  const appendToModeArray = useCallback((mode, field, item, maxLen) => {
    setModeStates(prev => {
      const arr = prev[mode][field];
      return {
        ...prev,
        [mode]: { ...prev[mode], [field]: [...arr.slice(-(maxLen - 1)), item] },
      };
    });
  }, []);

  // Process WebSocket message for a mode
  const processMessage = useCallback((mode, message) => {
    const outerType = message.type;
    const payload = message.data || message;
    const eventType = payload.event_type || outerType;

    if (outerType === 'heartbeat' || outerType === 'connection') return;

    switch (eventType) {
      case 'log':
      case 'trading_log':
        appendToModeArray(mode, 'logs', payload, 500);
        break;

      case 'positions':
        appendToModeArray(mode, 'logs', payload, 500);
        if (payload.data?.positions && Array.isArray(payload.data.positions)) {
          updateModeState(mode, { positions: payload.data.positions });
        }
        break;

      case 'account_value':
        appendToModeArray(mode, 'logs', payload, 500);
        if (payload.data?.account_value !== undefined) {
          const acctVal = parseFloat(payload.data.account_value) || 0;
          const cashVal = parseFloat(payload.data.cash) || 0;
          setModeStates(prev => ({
            ...prev,
            [mode]: {
              ...prev[mode],
              metrics: { ...(prev[mode].metrics || {}), accountValue: acctVal },
              portfolioHistory: [...prev[mode].portfolioHistory.slice(-299), {
                timestamp: payload.timestamp || Date.now(),
                total_value: acctVal, cash: cashVal,
                unrealized_pnl: 0, realized_pnl: 0,
              }],
            },
          }));
        }
        break;

      case 'portfolio_snapshot':
        appendToModeArray(mode, 'logs', payload, 500);
        if (payload.data) {
          const pData = payload.data;
          const updates = {};
          if (pData.lots && typeof pData.lots === 'object') {
            const allLots = [];
            for (const [symbol, lots] of Object.entries(pData.lots)) {
              if (Array.isArray(lots)) {
                lots.forEach(lot => allLots.push({
                  ...lot, symbol: lot.symbol || symbol,
                  quantity: parseFloat(lot.quantity) || 0,
                  entry_price: parseFloat(lot.entry_price) || 0,
                  cost_basis: parseFloat(lot.cost_basis) || 0,
                }));
              }
            }
            if (allLots.length > 0) updates.positions = allLots;
          }
          if (pData.performance) {
            setModeStates(prev => ({
              ...prev,
              [mode]: {
                ...prev[mode],
                ...updates,
                metrics: {
                  ...(prev[mode].metrics || {}),
                  totalPnL: parseFloat(pData.performance.total_pnl) || 0,
                  totalTrades: pData.performance.total_trades || 0,
                  winningTrades: pData.performance.winning_trades || 0,
                  losingTrades: pData.performance.losing_trades || 0,
                  winRate: parseFloat(pData.performance.win_rate) || 0,
                },
              },
            }));
          } else if (Object.keys(updates).length > 0) {
            updateModeState(mode, updates);
          }
        }
        break;

      case 'price_dataframe': {
        appendToModeArray(mode, 'logs', payload, 500);
        const dfPayload = payload.data || {};
        const dfRows = dfPayload.data;
        if (Array.isArray(dfRows) && dfRows.length > 0) {
          const titleMatch = (dfPayload.title || '').match(/Technical Indicators for (.+)/);
          const dfSymbol = titleMatch ? titleMatch[1].trim() : (dfRows[0].symbol || 'UNKNOWN');

          setModeStates(prev => {
            const prevPdf = prev[mode].priceDataframes;
            const existingPdf = prevPdf[dfSymbol] || [];
            const mergedPdf = [...existingPdf, ...dfRows].slice(-100);
            return {
              ...prev,
              [mode]: {
                ...prev[mode],
                priceDataframes: { ...prevPdf, [dfSymbol]: mergedPdf },
              },
            };
          });
        }
        break;
      }

      case 'exit_conditions':
        appendToModeArray(mode, 'logs', payload, 500);
        break;

      case 'portfolio_update':
      case 'portfolio_update_event':
        setModeStates(prev => {
          const updates = { portfolio: payload };
          if (payload.lots && Array.isArray(payload.lots)) updates.positions = payload.lots;
          if (payload.completed_trades && Array.isArray(payload.completed_trades)) updates.completedTrades = payload.completed_trades;
          if (payload.performance) {
            updates.metrics = {
              totalPnL: parseFloat(payload.performance.total_pnl) || 0,
              unrealizedPnL: parseFloat(payload.performance.unrealized_pnl) || 0,
              totalTrades: payload.performance.total_trades || 0,
              winningTrades: payload.performance.winning_trades || 0,
              losingTrades: payload.performance.losing_trades || 0,
              winRate: parseFloat(payload.performance.win_rate) || 0,
              accountValue: parseFloat(payload.total_value || payload.current_cash) || 0,
              totalReturnPct: parseFloat(payload.performance.total_return_pct) || 0,
            };
          }
          updates.portfolioHistory = [...prev[mode].portfolioHistory.slice(-299), {
            timestamp: payload.timestamp || Date.now(),
            unrealized_pnl: parseFloat(payload.performance?.unrealized_pnl) || 0,
            realized_pnl: parseFloat(payload.performance?.total_pnl) || 0,
            total_value: parseFloat(payload.total_value || payload.current_cash) || 0,
          }];
          return { ...prev, [mode]: { ...prev[mode], ...updates } };
        });
        break;

      case 'position_opened':
        if (payload.lot) {
          setModeStates(prev => {
            const exists = prev[mode].positions.some(p => p.lot_id === payload.lot.lot_id);
            if (exists) return prev;
            return {
              ...prev,
              [mode]: {
                ...prev[mode],
                positions: [...prev[mode].positions, payload.lot],
                logs: [...prev[mode].logs.slice(-499), {
                  event_type: 'log', level: 'INFO',
                  message: `Position opened: ${payload.lot?.symbol || 'unknown'} qty=${payload.lot?.quantity || 0}`,
                  timestamp: payload.timestamp || Date.now(),
                }],
              },
            };
          });
        }
        break;

      case 'trade_completed':
      case 'trade_update':
        if (payload.trade) {
          setModeStates(prev => {
            const exists = prev[mode].completedTrades.some(t =>
              t.trade_id === payload.trade.trade_id || t.lot_id === payload.trade.lot_id
            );
            if (exists) return prev;
            return {
              ...prev,
              [mode]: {
                ...prev[mode],
                completedTrades: [...prev[mode].completedTrades, payload.trade],
                positions: payload.trade.lot_id
                  ? prev[mode].positions.filter(p => p.lot_id !== payload.trade.lot_id)
                  : prev[mode].positions,
              },
            };
          });
        }
        break;

      case 'equity_update':
        setModeStates(prev => ({
          ...prev,
          [mode]: {
            ...prev[mode],
            portfolioHistory: [...prev[mode].portfolioHistory.slice(-299), {
              timestamp: payload.timestamp || Date.now(),
              total_value: parseFloat(payload.total_value) || 0,
              cash: parseFloat(payload.cash) || 0,
              positions_value: parseFloat(payload.positions_value) || 0,
              unrealized_pnl: 0, realized_pnl: 0,
            }],
          },
        }));
        break;

      case 'position_update':
        if (payload.positions) updateModeState(mode, { positions: payload.positions });
        break;

      case 'metrics_update':
        if (payload.metrics) {
          setModeStates(prev => ({
            ...prev,
            [mode]: { ...prev[mode], metrics: { ...(prev[mode].metrics || {}), ...payload.metrics } },
          }));
        }
        break;

      case 'indicator_values':
        if (payload.symbol && payload.columns && payload.rows) {
          setModeStates(prev => ({
            ...prev,
            [mode]: {
              ...prev[mode],
              indicatorData: {
                ...prev[mode].indicatorData,
                [payload.symbol]: { columns: payload.columns, rows: payload.rows, timestamp: payload.timestamp || Date.now() },
              },
            },
          }));
        }
        break;

      case 'status':
        console.log(`[${mode}] Task status:`, payload);
        break;

      default:
        console.log(`[${mode}] Unhandled event type:`, eventType, payload);
        appendToModeArray(mode, 'logs', {
          event_type: 'log', level: 'DEBUG',
          message: JSON.stringify(payload),
          timestamp: new Date().toISOString(),
        }, 500);
    }
  }, [updateModeState, appendToModeArray]);

  // WebSocket connection for a single mode
  const connectWebSocket = useCallback((mode, taskId, strategyId) => {
    const connectionId = taskId || strategyId;
    if (!connectionId) {
      console.warn(`[${mode}] No connection ID for WebSocket`);
      return;
    }

    const wsBaseUrl = getWebSocketUrl();
    const baseWsUrl = wsBaseUrl + '/ws/task/' + connectionId;
    // On first connect use "0" (all history); on reconnect resume from last received ID
    const getWsUrl = () => {
      const lastId = lastMessageIdRefs.current[mode];
      return lastId ? `${baseWsUrl}?last_id=${encodeURIComponent(lastId)}` : baseWsUrl;
    };
    const wsUrl = getWsUrl();

    // Skip if already connected to same URL
    if (wsRefs.current[mode]?.readyState === WebSocket.OPEN) {
      return;
    }

    // Close existing
    if (wsRefs.current[mode]) {
      wsRefs.current[mode].close(1000, 'Switching connection');
    }

    let reconnectTimeout = null;

    const doConnect = () => {
      const url = getWsUrl();
      console.log(`[${mode}] Connecting WebSocket to ${url}`);
      const ws = new WebSocket(url);
      wsRefs.current[mode] = ws;

      ws.onopen = () => {
        console.log(`[${mode}] WebSocket connected`);
        updateModeState(mode, { socketStatus: 'connected', socketError: null });
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          // Track last message ID for reconnection catch-up
          if (msg.id) {
            lastMessageIdRefs.current[mode] = msg.id;
          }
          processMessage(mode, msg);
        } catch (error) {
          console.error(`[${mode}] Error parsing WebSocket message:`, error);
        }
      };

      ws.onerror = () => {
        updateModeState(mode, { socketError: 'WebSocket connection failed', socketStatus: 'error' });
      };

      ws.onclose = (event) => {
        console.log(`[${mode}] WebSocket disconnected`, event.code, event.reason);
        updateModeState(mode, { socketStatus: 'disconnected' });
        if (isDeployedRefs.current[mode] && event.code !== 1000) {
          console.log(`[${mode}] Reconnecting in 3s...`);
          reconnectTimeout = setTimeout(() => {
            if (isDeployedRefs.current[mode]) doConnect();
          }, 3000);
        }
      };
    };

    doConnect();

    return () => {
      if (wsRefs.current[mode]) {
        wsRefs.current[mode].close(1000, 'Cleanup');
        wsRefs.current[mode] = null;
      }
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [processMessage, updateModeState]);

  // WebSocket effects (one per mode)
  useEffect(() => {
    const ms = modeStates.paper;
    if (!ms.isDeployed || (!ms.activeTaskId && !ms.deployedStrategy?.id)) {
      if (wsRefs.current.paper) {
        wsRefs.current.paper.close(1000, 'Not deployed');
        wsRefs.current.paper = null;
      }
      return;
    }
    const cleanup = connectWebSocket('paper', ms.activeTaskId, ms.deployedStrategy?.id);
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeStates.paper.isDeployed, modeStates.paper.activeTaskId, modeStates.paper.deployedStrategy?.id, connectWebSocket]);

  useEffect(() => {
    const ms = modeStates.live;
    if (!ms.isDeployed || (!ms.activeTaskId && !ms.deployedStrategy?.id)) {
      if (wsRefs.current.live) {
        wsRefs.current.live.close(1000, 'Not deployed');
        wsRefs.current.live = null;
      }
      return;
    }
    const cleanup = connectWebSocket('live', ms.activeTaskId, ms.deployedStrategy?.id);
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modeStates.live.isDeployed, modeStates.live.activeTaskId, modeStates.live.deployedStrategy?.id, connectWebSocket]);

  // Restore active sessions from backend
  const checkActiveSessions = useCallback(async () => {
    if (!authApi.isAuthenticated()) {
      console.log('DeployedStrategyContext: Not authenticated');
      return;
    }

    try {
      await userApi.getProfile();
      const response = await tradingApi.getActiveSessions();
      console.log('DeployedStrategyContext: Active sessions response:', response);

      const activeSessions = response.active_sessions || [];
      const modesWithSessions = new Set();

      for (const session of activeSessions) {
        const sessionMode = session.config?.mode || 'paper';
        modesWithSessions.add(sessionMode);

        let strategy;
        try {
          strategy = await strategyApi.getStrategy(session.strategy_id);
          if (strategy && !strategy.id && strategy._id) strategy.id = strategy._id;
        } catch (e) {
          console.error('[' + sessionMode + '] Failed to fetch strategy:', e);
          strategy = { id: session.strategy_id, name: session.strategy_name || 'Unknown Strategy', active: true };
        }
        if (!strategy.config && session.strategy_config) {
          strategy.config = session.strategy_config;
        }

        const provider = session.config?.data_provider || 'alpaca';
        const health = session.health || 'unknown';

        updateModeState(sessionMode, {
          deployedStrategy: strategy,
          isDeployed: true,
          activeTaskId: session.task_id,
          dataProvider: provider,
          sessionHealth: health,
          deploymentTime: session.started_at ? new Date(session.started_at).getTime() : Date.now(),
        });

        // Restore portfolio state
        try {
          const sessionDetails = await tradingApi.getSessionDetails(session.strategy_id, sessionMode);
          if (sessionDetails?.portfolio) {
            const pData = sessionDetails.portfolio;
            const updates = {};
            if (pData.lots && typeof pData.lots === 'object') {
              const allLots = [];
              for (const [symbol, lots] of Object.entries(pData.lots)) {
                if (Array.isArray(lots)) {
                  lots.forEach(lot => allLots.push({
                    ...lot, symbol: lot.symbol || symbol,
                    quantity: parseFloat(lot.quantity) || 0,
                    entry_price: parseFloat(lot.entry_price) || 0,
                    cost_basis: parseFloat(lot.cost_basis) || 0,
                  }));
                }
              }
              if (allLots.length > 0) updates.positions = allLots;
            }
            if (pData.completed_trades && Array.isArray(pData.completed_trades)) {
              updates.completedTrades = pData.completed_trades;
            }
            if (pData.performance) {
              updates.metrics = {
                totalPnL: parseFloat(pData.performance.total_pnl) || 0,
                totalTrades: pData.performance.total_trades || 0,
                winningTrades: pData.performance.winning_trades || 0,
                losingTrades: pData.performance.losing_trades || 0,
                winRate: parseFloat(pData.performance.win_rate) || 0,
              };
            }
            if (Object.keys(updates).length > 0) updateModeState(sessionMode, updates);
            console.log('[' + sessionMode + '] Restored portfolio state');
          }
        } catch (err) {
          console.warn('[' + sessionMode + '] Could not restore portfolio:', err);
        }
      }

      // Clear modes with no active session
      for (const m of ['paper', 'live']) {
        if (!modesWithSessions.has(m)) {
          setModeStates(prev => {
            if (prev[m]?.isDeployed) {
              console.log('[' + m + '] Clearing stale deployment state');
              return { ...prev, [m]: { ...DEFAULT_MODE_STATE } };
            }
            return prev;
          });
        }
      }
    } catch (err) {
      console.error('DeployedStrategyContext: Error checking active sessions:', err);
    }
  }, [updateModeState]);

  // Login listener
  useEffect(() => {
    const handleLogin = () => checkActiveSessions();
    window.addEventListener('auth:login', handleLogin);
    return () => window.removeEventListener('auth:login', handleLogin);
  }, [checkActiveSessions]);

  // Initial check
  useEffect(() => {
    checkActiveSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist to localStorage
  useEffect(() => {
    const toSave = {};
    for (const m of ['paper', 'live']) {
      const ms = modeStates[m];
      if (ms.deployedStrategy && ms.isDeployed) {
        toSave[m] = {
          strategy: ms.deployedStrategy,
          isDeployed: true,
          dataProvider: ms.dataProvider,
          deploymentTime: ms.deploymentTime || Date.now(),
          activeTaskId: ms.activeTaskId,
        };
      }
    }
    if (Object.keys(toSave).length > 0) {
      localStorage.setItem('tradingModeStates', JSON.stringify(toSave));
    } else {
      localStorage.removeItem('tradingModeStates');
    }
  }, [modeStates]);

  // Actions
  const setDeploymentState = useCallback((strategy, taskId, provider = 'alpaca', tradingMode = 'paper') => {
    updateModeState(tradingMode, {
      ...DEFAULT_MODE_STATE,
      deployedStrategy: strategy,
      isDeployed: true,
      activeTaskId: taskId,
      dataProvider: provider,
      deploymentTime: Date.now(),
    });
  }, [updateModeState]);

  const deployStrategy = useCallback((strategy, provider = 'alpaca', tradingMode = 'paper') => {
    updateModeState(tradingMode, {
      ...DEFAULT_MODE_STATE,
      isDeployed: true,
      dataProvider: provider,
      deploymentTime: Date.now(),
    });
  }, [updateModeState]);

  const stopStrategy = useCallback((tradingMode = 'paper') => {
    isDeployedRefs.current[tradingMode] = false;
    lastMessageIdRefs.current[tradingMode] = null;
    if (wsRefs.current[tradingMode]) {
      wsRefs.current[tradingMode].close(1000, 'User stopped strategy');
      wsRefs.current[tradingMode] = null;
    }
    updateModeState(tradingMode, {
      isDeployed: false,
      activeTaskId: null,
      socketStatus: 'disconnected',
    });
  }, [updateModeState]);

  const clearDeployment = useCallback((tradingMode = 'paper') => {
    lastMessageIdRefs.current[tradingMode] = null;
    updateModeState(tradingMode, { ...DEFAULT_MODE_STATE });
  }, [updateModeState]);

  const setModeDataProvider = useCallback((tradingMode, provider) => {
    updateModeState(tradingMode, { dataProvider: provider });
  }, [updateModeState]);

  // Context value
  const value = useMemo(() => ({
    modeStates,
    setDeploymentState,
    deployStrategy,
    stopStrategy,
    clearDeployment,
    setModeDataProvider,
  }), [modeStates, setDeploymentState, deployStrategy, stopStrategy, clearDeployment, setModeDataProvider]);

  return (
    <DeployedStrategyContext.Provider value={value}>
      {children}
    </DeployedStrategyContext.Provider>
  );
};
