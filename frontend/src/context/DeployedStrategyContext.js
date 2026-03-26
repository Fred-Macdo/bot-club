import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import { getTradingStatus, tradingApi, authApi, userApi, strategyApi } from '../api/Client';
import { getWebSocketUrl } from '../utils/apiConfig';

const DeployedStrategyContext = createContext();

export const useDeployedStrategy = () => {
  const context = useContext(DeployedStrategyContext);
  if (!context) {
    throw new Error('useDeployedStrategy must be used within a DeployedStrategyProvider');
  }
  return context;
};

export const DeployedStrategyProvider = ({ children }) => {
  // Initialize state from localStorage for fast hydration on refresh
  const getInitialState = () => {
    try {
      const saved = localStorage.getItem('deployedStrategy');
      if (saved) {
        const parsed = JSON.parse(saved);
        //console.log('DeployedStrategyContext: Hydrating from localStorage:', parsed);
        return parsed;
      }
    } catch (e) {
      console.error('DeployedStrategyContext: Error parsing localStorage:', e);
    }
    return null;
  };

  const initialState = getInitialState();
  
  const [deployedStrategy, setDeployedStrategy] = useState(initialState?.strategy || null);
  const [isDeployed, setIsDeployed] = useState(initialState?.isDeployed || false);
  const [dataProvider, setDataProvider] = useState(initialState?.dataProvider || 'alpaca');
  const [mode, setMode] = useState(initialState?.mode || 'paper'); // Track 'paper' or 'live'
  const [deploymentTime, setDeploymentTime] = useState(initialState?.deploymentTime || null);

  // --- Socket State (Moved from useTradingSocket) ---
  const [logs, setLogs] = useState([]);
  const [socketStatus, setSocketStatus] = useState('disconnected');
  const [socketError, setSocketError] = useState(null);
  const [trades, setTrades] = useState([]);
  const [completedTrades, setCompletedTrades] = useState([]);
  const [positions, setPositions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [portfolio, setPortfolio] = useState(null); // Current portfolio state
  const [portfolioHistory, setPortfolioHistory] = useState([]); // History of portfolio snapshots
  const [indicatorData, setIndicatorData] = useState({}); // { symbol: { columns, rows } }
  
  // Track the current task ID for WebSocket connection - also hydrate from localStorage
  const [activeTaskId, setActiveTaskId] = useState(initialState?.activeTaskId || null);
  
  const webSocket = useRef(null);

  // Use a ref to track isDeployed state for access inside async callbacks
  const isDeployedRef = useRef(isDeployed);
  useEffect(() => {
    isDeployedRef.current = isDeployed;
  }, [isDeployed]);

  // Listener for re-login events to trigger reconnection
  useEffect(() => {
    const handleLogin = () => {
      console.log("DeployedStrategyContext: Auth login detected, re-checking sessions...");
      // Re-run the active session check
      checkActiveSessions();
    };

    window.addEventListener('auth:login', handleLogin);
    return () => window.removeEventListener('auth:login', handleLogin);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Helper to check sessions (moved out of useEffect to be reusable)
  const checkActiveSessions = async () => {
      if (!authApi.isAuthenticated()) {
        console.log("DeployedStrategyContext: User not authenticated, checking if we should preserve state.");
        if (isDeployed) {
           console.log("DeployedStrategyContext: Preserving deployment state despite auth logout. Will reconnect on login.");
        }
        return;
      }
      
      try {
        const userProfile = await userApi.getProfile();
        const userId = userProfile.id || userProfile._id || userProfile.user_id; 
        
        console.log(`DeployedStrategyContext: Checking active sessions for user: ${userId}`);
        const response = await tradingApi.getActiveSessions(userId);
        console.log('DeployedStrategyContext: Active sessions response:', response);

        if (response.active_sessions && response.active_sessions.length > 0) {
           const session = response.active_sessions[0];
           console.log("DeployedStrategyContext: Found active session, reconnecting:", session);
           
           if (isDeployed && activeTaskId) {
             if (session.task_id && session.task_id !== activeTaskId) {
               console.log(`DeployedStrategyContext: Updating task_id from ${activeTaskId} to ${session.task_id}`);
               setActiveTaskId(session.task_id);
             } else {
               console.log("DeployedStrategyContext: Already have correct task_id, WebSocket should connect.");
             }
           } else {
             // No localStorage state, or missing task_id - do full setup
             let strategy;
             try {
               strategy = await strategyApi.getStrategy(session.strategy_id);
               if (strategy && !strategy.id && strategy._id) {
                 strategy.id = strategy._id;
               }
             } catch (e) {
               console.error("DeployedStrategyContext: Failed to fetch strategy details for active session", e);
               strategy = { 
                 id: session.strategy_id, 
                 name: session.strategy_name || "Unknown Strategy",
                 active: true
               };
             }
             
             // Hydrate state from backend session
             const provider = session.config?.data_provider || 'alpaca';
             const mode = session.config?.mode || 'paper';
             
             // Use public setDeploymentState logic manually here to avoid circular dep or issues
             // setDeploymentState cannot be called during render, but we are in async callback here
             setDeployedStrategy(strategy);
             setIsDeployed(true);
             setActiveTaskId(session.task_id); // Set task ID for WS connection
             setMode(mode);
             setDataProvider(provider);
             // Timestamp from session might be ISO string
             setDeploymentTime(session.started_at ? new Date(session.started_at).getTime() : Date.now());
             
             // Load saved portfolio state from session details so UI isn't empty on reconnect
             try {
               const sessionDetails = await tradingApi.getSessionDetails(session.strategy_id, userId);
               if (sessionDetails?.portfolio) {
                 const pData = sessionDetails.portfolio;
                 // Restore positions from lots
                 if (pData.lots && typeof pData.lots === 'object') {
                   const allLots = [];
                   for (const [symbol, lots] of Object.entries(pData.lots)) {
                     if (Array.isArray(lots)) {
                       lots.forEach(lot => allLots.push({
                         ...lot,
                         symbol: lot.symbol || symbol,
                         quantity: parseFloat(lot.quantity) || 0,
                         entry_price: parseFloat(lot.entry_price) || 0,
                         cost_basis: parseFloat(lot.cost_basis) || 0,
                       }));
                     }
                   }
                   if (allLots.length > 0) setPositions(allLots);
                 }
                 // Restore completed trades
                 if (pData.completed_trades && Array.isArray(pData.completed_trades)) {
                   setCompletedTrades(pData.completed_trades);
                 }
                 // Restore performance metrics
                 if (pData.performance) {
                   setMetrics({
                     totalPnL: parseFloat(pData.performance.total_pnl) || 0,
                     totalTrades: pData.performance.total_trades || 0,
                     winningTrades: pData.performance.winning_trades || 0,
                     losingTrades: pData.performance.losing_trades || 0,
                     winRate: parseFloat(pData.performance.win_rate) || 0,
                   });
                 }
                 console.log("DeployedStrategyContext: Restored portfolio state from session.");
               }
             } catch (portfolioErr) {
               console.warn("DeployedStrategyContext: Could not restore portfolio from session:", portfolioErr);
             }
           }

        } else {
            console.log("DeployedStrategyContext: No active sessions found on backend.");
            // If backend says no session, but we thought we were deployed, then we should clear.
            // This handles the case where the task died while we were logged out.
            if (isDeployed) {
              console.log("DeployedStrategyContext: Clearing stale deployment state - backend has no session.");
              setIsDeployed(false);
              setActiveTaskId(null);
              setDeployedStrategy(null);
              localStorage.removeItem('deployedStrategy');
            }
        }
      } catch (err) {
        console.error("DeployedStrategyContext: Error checking active sessions:", err);
      }
    };

  // Initial check on mount
  useEffect(() => {
    checkActiveSessions();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps


  // --- WebSocket Logic ---
  useEffect(() => {
    // Only connect if deployed and we have a task ID (preferred) or strategy ID
    // If activeTaskId is set (from active session check), use it. 
    // Otherwise fallback to strategy ID if task ID not available? 
    // BUT backend now expects task_id. If we start a new strategy, we need to know the task_id.
    // The deployStrategy function needs to capture the task_id from the response?
    // Let's assume activeTaskId is critical now.
    
    if (!isDeployed || (!activeTaskId && !deployedStrategy?.id)) {
      if (webSocket.current) {
        webSocket.current.close(1000, "Component unmounting or stopped");
        webSocket.current = null;
      }
      return;
    }

    // We prefer activeTaskId if available, otherwise strategyId (legacy behavior or if task ID missing)
    // But backend route is /ws/trading/{task_id}. We MUST provide a task ID if that's what backend expects.
    // However, if we just started trading, where do we get task_id?
    // We need to update deployStrategy to set it.
    
    // Prefer activeTaskId. If not available, we might fail to connect if backend requires task_id.
    // But for legacy support or race conditions, we check.
    if (!activeTaskId) {
        console.warn("DeployedStrategyContext: No active task ID found for WebSocket. Connection might fail if backend requires task_id.");
    }
    
    const connectionId = activeTaskId || deployedStrategy?.id;
    
    // Avoid reconnecting if already connected to the same ID
    const wsBaseUrl = getWebSocketUrl();
    console.log("DeployedStrategyContext: WebSocket base URL:", wsBaseUrl);
    // Update to match backend route: /ws/task/{task_id}
    const wsUrl = `${wsBaseUrl}/ws/task/${connectionId}`;

    if (webSocket.current && webSocket.current.url === wsUrl && webSocket.current.readyState === WebSocket.OPEN) {
        return;
    }
    
    // Close existing if different
    if (webSocket.current) {
        webSocket.current.close(1000, "Switching connection");
    }
    
    let reconnectTimeout = null;

    const connectSocket = () => {
        console.log(`Connecting socket for ID: ${connectionId}`);
        const ws = new WebSocket(wsUrl);
        console.log("DeployedStrategyContext: WebSocket URL:", wsUrl);
        webSocket.current = ws;

        ws.onopen = () => {
          console.log('WebSocket connected');
          setSocketStatus('connected');
          setSocketError(null);
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            // Messages arrive as { id, type, data: { event_type, ... } }
            // The actual payload is in message.data, and event_type is inside the payload
            const outerType = message.type;
            const payload = message.data || message;
            const eventType = payload.event_type || outerType;
            
            // Skip non-data messages
            if (outerType === 'heartbeat' || outerType === 'connection') return;
            
            switch (eventType) {
              // --- Log-type events (display in TradingLogs via LogRenderer) ---
              case 'log':
              case 'trading_log':
                setLogs(prev => [...prev.slice(-499), payload]);
                break;
                
              case 'positions':
                // Add to logs for LogRenderer display
                setLogs(prev => [...prev.slice(-499), payload]);
                // Also extract structured positions data for Positions component
                if (payload.data && payload.data.positions && Array.isArray(payload.data.positions)) {
                  setPositions(payload.data.positions);
                }
                break;
                
              case 'account_value':
                // Add to logs for LogRenderer display
                setLogs(prev => [...prev.slice(-499), payload]);
                // Also extract structured account value for metrics and equity chart
                if (payload.data && payload.data.account_value !== undefined) {
                  const acctVal = parseFloat(payload.data.account_value) || 0;
                  const cashVal = parseFloat(payload.data.cash) || 0;
                  setMetrics(prev => ({
                    ...(prev || {}),
                    accountValue: acctVal,
                  }));
                  // Add equity data point for charting
                  setPortfolioHistory(prev => [...prev.slice(-299), {
                    timestamp: payload.timestamp || Date.now(),
                    total_value: acctVal,
                    cash: cashVal,
                    unrealized_pnl: 0,
                    realized_pnl: 0,
                  }]);
                }
                break;

              case 'portfolio_snapshot':
                // Add to logs for PortfolioSnapshotLog renderer
                setLogs(prev => [...prev.slice(-499), payload]);
                // Also extract portfolio data to populate state
                if (payload.data) {
                  const pData = payload.data;
                  // Extract positions from lots (dict of symbol -> lots[])
                  if (pData.lots && typeof pData.lots === 'object') {
                    const allLots = [];
                    for (const [symbol, lots] of Object.entries(pData.lots)) {
                      if (Array.isArray(lots)) {
                        lots.forEach(lot => allLots.push({
                          ...lot,
                          symbol: lot.symbol || symbol,
                          quantity: parseFloat(lot.quantity) || 0,
                          entry_price: parseFloat(lot.entry_price) || 0,
                          cost_basis: parseFloat(lot.cost_basis) || 0,
                        }));
                      }
                    }
                    if (allLots.length > 0) {
                      setPositions(allLots);
                    }
                  }
                  // Extract performance metrics
                  if (pData.performance) {
                    setMetrics(prev => ({
                      ...(prev || {}),
                      totalPnL: parseFloat(pData.performance.total_pnl) || 0,
                      totalTrades: pData.performance.total_trades || 0,
                      winningTrades: pData.performance.winning_trades || 0,
                      losingTrades: pData.performance.losing_trades || 0,
                      winRate: parseFloat(pData.performance.win_rate) || 0,
                    }));
                  }
                }
                break;

              case 'price_dataframe':
              case 'exit_conditions':
                // These are display-only log events rendered by LogRenderer
                setLogs(prev => [...prev.slice(-499), payload]);
                break;
                
              // --- Portfolio update from persistence layer ---
              case 'portfolio_update':
              case 'portfolio_update_event':
                setPortfolio(payload);
                
                // Extract positions from lots
                if (payload.lots && Array.isArray(payload.lots)) {
                  setPositions(payload.lots);
                }
                
                // Extract completed trades
                if (payload.completed_trades && Array.isArray(payload.completed_trades)) {
                  setCompletedTrades(payload.completed_trades);
                }
                
                // Extract performance metrics
                if (payload.performance) {
                  setMetrics({
                    totalPnL: parseFloat(payload.performance.total_pnl) || 0,
                    unrealizedPnL: parseFloat(payload.performance.unrealized_pnl) || 0,
                    totalTrades: payload.performance.total_trades || 0,
                    winningTrades: payload.performance.winning_trades || 0,
                    losingTrades: payload.performance.losing_trades || 0,
                    winRate: parseFloat(payload.performance.win_rate) || 0,
                    accountValue: parseFloat(payload.total_value || payload.current_cash) || 0,
                    totalReturnPct: parseFloat(payload.performance.total_return_pct) || 0,
                  });
                }
                
                // Add to portfolio history for charting
                setPortfolioHistory(prev => [...prev.slice(-299), {
                  timestamp: payload.timestamp || Date.now(),
                  unrealized_pnl: parseFloat(payload.performance?.unrealized_pnl) || 0,
                  realized_pnl: parseFloat(payload.performance?.total_pnl) || 0,
                  total_value: parseFloat(payload.total_value || payload.current_cash) || 0,
                }]);
                break;
              
              // --- Position opened from persistence layer ---
              case 'position_opened':
                if (payload.lot) {
                  setPositions(prev => {
                    const exists = prev.some(p => p.lot_id === payload.lot.lot_id);
                    if (exists) return prev;
                    return [...prev, payload.lot];
                  });
                }
                // Also add as a log entry
                setLogs(prev => [...prev.slice(-499), {
                  event_type: 'log',
                  level: 'INFO',
                  message: `Position opened: ${payload.lot?.symbol || 'unknown'} qty=${payload.lot?.quantity || 0}`,
                  timestamp: payload.timestamp || Date.now()
                }]);
                break;
                
              // --- Trade completed from persistence layer ---
              case 'trade_completed':
              case 'trade_update':
                if (payload.trade) {
                  setCompletedTrades(prev => {
                    const exists = prev.some(t => 
                      t.trade_id === payload.trade.trade_id || 
                      t.lot_id === payload.trade.lot_id
                    );
                    if (exists) return prev;
                    return [...prev, payload.trade];
                  });
                  // Remove the closed lot from positions
                  if (payload.trade.lot_id) {
                    setPositions(prev => prev.filter(p => p.lot_id !== payload.trade.lot_id));
                  }
                }
                break;
              
              // --- Equity curve update from persistence layer ---
              case 'equity_update':
                setPortfolioHistory(prev => [...prev.slice(-299), {
                  timestamp: payload.timestamp || Date.now(),
                  total_value: parseFloat(payload.total_value) || 0,
                  cash: parseFloat(payload.cash) || 0,
                  positions_value: parseFloat(payload.positions_value) || 0,
                  unrealized_pnl: 0,
                  realized_pnl: 0,
                }]);
                break;
                
              case 'position_update':
                if (payload.positions) {
                  setPositions(payload.positions);
                }
                break;
                
              case 'metrics_update':
                if (payload.metrics) {
                  setMetrics(prev => ({ ...prev, ...payload.metrics }));
                }
                break;
                
              case 'indicator_values':
                // Structured indicator time-series for charting
                if (payload.symbol && payload.columns && payload.rows) {
                  setIndicatorData(prev => ({
                    ...prev,
                    [payload.symbol]: {
                      columns: payload.columns,
                      rows: payload.rows,
                      timestamp: payload.timestamp || Date.now(),
                    }
                  }));
                }
                break;

              case 'status':
                // Task status events (started, completed, error)
                console.log('Task status:', payload);
                break;
                
              default:
                console.log('Unhandled event type:', eventType, payload);
                setLogs(prev => [...prev.slice(-499), { 
                  event_type: 'log',
                  level: 'DEBUG', 
                  message: JSON.stringify(payload),
                  timestamp: new Date().toISOString()
                }]);
            }
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        ws.onerror = (err) => {
          console.error('WebSocket error:', err);
          setSocketError('WebSocket connection failed');
          setSocketStatus('error');
        };

        ws.onclose = (event) => {
          console.log('WebSocket disconnected', event.code, event.reason);
          setSocketStatus('disconnected');
          
          // Attempt reconnect if not closed cleanly and we are still deployed
          // Use Ref to check current state, bypassing closure staleness
          if (isDeployedRef.current && event.code !== 1000) {
              console.log("Attempting to reconnect in 3s...");
              reconnectTimeout = setTimeout(() => {
                  // Double check state before reconnecting
                  if (isDeployedRef.current) {
                      connectSocket();
                  }
              }, 3000);
          }
        };
    };

    connectSocket();

    return () => {
      if (webSocket.current) {
        webSocket.current.close(1000, "Component unmounting");
      }
      if (reconnectTimeout) {
          clearTimeout(reconnectTimeout);
      }
    };
  }, [isDeployed, deployedStrategy?.id, deployedStrategy?._id, activeTaskId]);

  // Save to localStorage (including activeTaskId for reconnection on refresh)
  useEffect(() => {
    if (deployedStrategy && isDeployed) {
      localStorage.setItem('deployedStrategy', JSON.stringify({
        strategy: deployedStrategy,
        isDeployed,
        dataProvider,
        mode,
        deploymentTime: deploymentTime || Date.now(),
        activeTaskId: activeTaskId  // Save task ID for reconnection
      }));
    } else if (!isDeployed) {
      localStorage.removeItem('deployedStrategy');
    }
  }, [deployedStrategy, isDeployed, dataProvider, mode, deploymentTime, activeTaskId]);

  const deployStrategy = (strategy, provider = 'alpaca', tradingMode = 'paper') => {
    // Reset previous session data
    setLogs([]);
    setTrades([]);
    setCompletedTrades([]);
    setPositions([]);
    setMetrics(null);
    setPortfolio(null);
    setPortfolioHistory([]);
    
    setDeployedStrategy(strategy);
    setIsDeployed(true);
    setDataProvider(provider);
    setMode(tradingMode);
    setDeploymentTime(Date.now());
    
    // NOTE: The actual API call to start trading is usually done by the component (e.g. PaperTrade.js)
    // which then calls this function to update context state.
    // However, we need to know the task_id here for WebSocket connection.
    // Ideally, deployStrategy should accept task_id as an argument or we should refactor how deployment is triggered.
    // 
    // If the component calls `apiClient.deployStrategy` and then calls this context method,
    // it should pass the task_id from the API response.
  };

  // New method to handle deployment with task ID
  const setDeploymentState = (strategy, taskId, provider = 'alpaca', tradingMode = 'paper') => {
      // Reset previous session data
      setLogs([]);
      setTrades([]);
      setCompletedTrades([]);
      setPositions([]);
      setMetrics(null);
      setPortfolio(null);
      setPortfolioHistory([]);
      
      setDeployedStrategy(strategy);
      setIsDeployed(true);
      setActiveTaskId(taskId); // Set the task ID for WS
      setDataProvider(provider);
      setMode(tradingMode);
      setDeploymentTime(Date.now());
  };

  const stopStrategy = () => {
    isDeployedRef.current = false; // Immediate update to prevent race conditions in WS callbacks
    setIsDeployed(false);
    setActiveTaskId(null);
    setSocketStatus('disconnected');
    if (webSocket.current) {
        // Explicitly close with normal closure code (1000) to prevent reconnect attempts
        webSocket.current.close(1000, "User stopped strategy");
        webSocket.current = null;
    }
  };

  const clearDeployment = () => {
    setDeployedStrategy(null);
    setIsDeployed(false);
    localStorage.removeItem('deployedStrategy');
  };

  const value = {
    // Deployment State
    deployedStrategy,
    isDeployed,
    dataProvider,
    mode,
    deploymentTime,
    activeTaskId, // Export activeTaskId
    deployStrategy,
    stopStrategy,
    clearDeployment,
    setDataProvider,
    setDeploymentState, // Export new method
    
    // Socket Data
    logs,
    socketStatus,
    socketError,
    trades,
    completedTrades,
    positions,
    metrics,
    portfolio,
    portfolioHistory,
    indicatorData,  // Indicator time-series for charting
  };

  return (
    <DeployedStrategyContext.Provider value={value}>
      {children}
    </DeployedStrategyContext.Provider>
  );
};

