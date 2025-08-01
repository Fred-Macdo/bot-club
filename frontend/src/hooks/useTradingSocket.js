import { useState, useEffect, useRef } from 'react';

const useTradingSocket = (strategyId) => {
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState('disconnected');
  const [error, setError] = useState(null);
  const webSocket = useRef(null);

  useEffect(() => {
    if (!strategyId) return;

    // The WebSocket URL should point to your backend_services container
    // Make sure to replace `localhost` with the correct hostname if needed
    const wsUrl = `ws://localhost:8001/ws/trading/${strategyId}`;
    
    webSocket.current = new WebSocket(wsUrl);

    webSocket.current.onopen = () => {
      console.log(`WebSocket connected for strategy ${strategyId}`);
      setStatus('connected');
      setError(null);
    };

    webSocket.current.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === 'status') {
          setStatus(message.data.status);
        } else if (message.type === 'log') {
          // Handle the structured log message
          setLogs((prevLogs) => [message.data, ...prevLogs].slice(0, 200)); // Keep last 200 logs
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

  return { logs, status, error };
};

export default useTradingSocket; 