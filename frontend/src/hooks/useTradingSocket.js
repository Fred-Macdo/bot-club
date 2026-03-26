import { useState, useEffect, useRef } from 'react';
import { getWebSocketUrl } from '../utils/apiConfig';

const useTradingSocket = (strategyId) => {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('disconnected');
  const [error, setError] = useState(null);
  const [trades, setTrades] = useState([]);
  const [completedTrades, setCompletedTrades] = useState([]);
  const [positions, setPositions] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const webSocket = useRef(null);

  useEffect(() => {
    if (!strategyId) {
      // Reset state when no strategy is selected
      setLogs([]);
      setTrades([]);
      setCompletedTrades([]);
      setPositions([]);
      setMetrics(null);
      return;
    }

    // Get the WebSocket base URL from config and append the strategy endpoint
    const wsBaseUrl = getWebSocketUrl();
    const wsUrl = `${wsBaseUrl}/ws/trading/${strategyId}`;
    
    webSocket.current = new WebSocket(wsUrl);

    webSocket.current.onopen = () => {
      console.log(`WebSocket connected for strategy ${strategyId}`);
      console.log(`Subscribed to websocket at ${wsUrl}`);
      setStatus('connected');
      setError(null);
    };

    webSocket.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('Received WebSocket message type:', message.type);
        if (message.type === 'status') {
          setStatus(message.data.status);
        } else if (message.type === 'log') {
          // Handle the structured log message
          setLogs((prevLogs) => [message.data, ...prevLogs].slice(0, 200)); // Keep last 200 logs
        } else if (message.type === 'trade') {
          // Handle simple trade transaction events (buy/sell)
          setTrades((prevTrades) => [message.data, ...prevTrades]);
        } else if (message.type === 'completed_trade') {
          // Handle completed trades with full entry/exit/P&L details
          setCompletedTrades((prevTrades) => [message.data, ...prevTrades]);
        } else if (message.type === 'position') {
          // Handle position updates
          setPositions(message.data.positions || []);
        } else if (message.type === 'metrics') {
          // Handle performance metrics
          setMetrics(message.data);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };

    webSocket.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('WebSocket connection failed.');
      setStatus('error');
    };

    webSocket.current.onclose = () => {
      console.log(`WebSocket disconnected for strategy ${strategyId}`);
      setStatus('disconnected');
    };

    // Cleanup on unmount
    return () => {
      if (webSocket.current) {
        webSocket.current.close();
      }
    };
  }, [strategyId]);

  return { logs, status, error, trades, completedTrades, positions, metrics };
};

export default useTradingSocket; 