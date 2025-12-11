import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { getTradingStatus } from '../api/Client';
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
  const [deployedStrategy, setDeployedStrategy] = useState(null);
  const [isDeployed, setIsDeployed] = useState(false);
  const [dataProvider, setDataProvider] = useState('alpaca');
  const [mode, setMode] = useState('paper'); // Track 'paper' or 'live'
  const [deploymentTime, setDeploymentTime] = useState(null);

  // --- Socket State (Moved from useTradingSocket) ---
  const [logs, setLogs] = useState([]);
  const [socketStatus, setSocketStatus] = useState('disconnected');
  const [socketError, setSocketError] = useState(null);
  const [trades, setTrades] = useState([]);
  const [completedTrades, setCompletedTrades] = useState([]);
  const [positions, setPositions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  
  const webSocket = useRef(null);

  // Load deployed strategy from localStorage on mount
  useEffect(() => {
    const verifyAndRestoreDeployment = async () => {
      try {
        const stored = localStorage.getItem('deployedStrategy');
        if (!stored) return;
        
        const data = JSON.parse(stored);
        
        // Check expiry (24h)
        const now = Date.now();
        const deployedAt = data.deploymentTime || 0;
        if ((now - deployedAt) / (1000 * 60 * 60) >= 24) {
          localStorage.removeItem('deployedStrategy');
          return;
        }
        
        // Verify with backend
        if (data.isDeployed && data.strategy?.id) {
          console.log('Verifying deployment...');
          const statusResult = await getTradingStatus(data.strategy.id);
          
          if (statusResult.success && statusResult.data.is_running) {
            setDeployedStrategy(data.strategy);
            setIsDeployed(true);
            setDataProvider(data.dataProvider || 'alpaca');
            setMode(data.mode || 'paper');
            setDeploymentTime(data.deploymentTime);
          } else {
            localStorage.removeItem('deployedStrategy');
          }
        }
      } catch (error) {
        console.error('Error verifying deployment:', error);
      }
    };
    
    verifyAndRestoreDeployment();
  }, []);

  // --- WebSocket Logic ---
  useEffect(() => {
    // Only connect if deployed and we have an ID
    if (!isDeployed || !deployedStrategy?.id) {
      if (webSocket.current) {
        webSocket.current.close();
        webSocket.current = null;
      }
      return;
    }

    // Avoid reconnecting if already connected to the same strategy
    if (webSocket.current && webSocket.current.readyState === WebSocket.OPEN) {
        return;
    }

    const wsBaseUrl = getWebSocketUrl();
    const wsUrl = `${wsBaseUrl}/ws/trading/${deployedStrategy.id}`;
    
    console.log(`Connecting socket for strategy: ${deployedStrategy.id}`);
    webSocket.current = new WebSocket(wsUrl);

    webSocket.current.onopen = () => {
      console.log('WebSocket connected');
      setSocketStatus('connected');
      setSocketError(null);
    };

    webSocket.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.type === 'status') {
          setSocketStatus(message.data.status);
        } else if (message.type === 'log') {
          setLogs((prev) => [message.data, ...prev].slice(0, 200));
        } else if (message.type === 'trade') {
          setTrades((prev) => [message.data, ...prev]);
        } else if (message.type === 'completed_trade') {
          setCompletedTrades((prev) => [message.data, ...prev]);
        } else if (message.type === 'position') {
          setPositions(message.data.positions || []);
        } else if (message.type === 'metrics') {
          setMetrics(message.data);
        }
      } catch (e) {
        console.error('Socket parse error:', e);
      }
    };

    webSocket.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setSocketError('WebSocket connection failed');
      setSocketStatus('error');
    };

    webSocket.current.onclose = () => {
      console.log('WebSocket disconnected');
      setSocketStatus('disconnected');
    };

    return () => {
      if (webSocket.current) {
        webSocket.current.close();
      }
    };
  }, [isDeployed, deployedStrategy?.id]);

  // Save to localStorage
  useEffect(() => {
    if (deployedStrategy && isDeployed) {
      localStorage.setItem('deployedStrategy', JSON.stringify({
        strategy: deployedStrategy,
        isDeployed,
        dataProvider,
        mode,
        deploymentTime: deploymentTime || Date.now()
      }));
    } else if (!isDeployed) {
      localStorage.removeItem('deployedStrategy');
    }
  }, [deployedStrategy, isDeployed, dataProvider, mode, deploymentTime]);

  const deployStrategy = (strategy, provider = 'alpaca', tradingMode = 'paper') => {
    // Reset previous session data
    setLogs([]);
    setTrades([]);
    setCompletedTrades([]);
    setPositions([]);
    setMetrics(null);
    
    setDeployedStrategy(strategy);
    setIsDeployed(true);
    setDataProvider(provider);
    setMode(tradingMode);
    setDeploymentTime(Date.now());
  };

  const stopStrategy = () => {
    setIsDeployed(false);
    // Socket will be closed by the useEffect cleanup
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
    deployStrategy,
    stopStrategy,
    clearDeployment,
    setDataProvider,
    
    // Socket Data
    logs,
    socketStatus,
    socketError,
    trades,
    completedTrades,
    positions,
    metrics
  };

  return (
    <DeployedStrategyContext.Provider value={value}>
      {children}
    </DeployedStrategyContext.Provider>
  );
};

