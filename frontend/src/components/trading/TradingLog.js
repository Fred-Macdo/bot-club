import React from 'react';
import useTradingSocket from '../../hooks/useTradingSocket';

const TradingLog = ({ strategyId }) => {
  const { logs, status, error } = useTradingSocket(strategyId);

  return (
    <div style={{ 
      backgroundColor: '#2d3748', 
      color: 'white', 
      padding: '1rem', 
      borderRadius: '8px', 
      fontFamily: 'monospace',
      height: '400px',
      overflowY: 'scroll',
      display: 'flex',
      flexDirection: 'column-reverse' // To keep latest logs at the bottom
    }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ marginBottom: '0.5rem' }}>
          <strong>Status:</strong> <span style={{ color: status === 'connected' ? '#48bb78' : '#f56565' }}>{status}</span>
        </div>
        {error && <div style={{ color: '#f56565', marginBottom: '0.5rem' }}><strong>Error:</strong> {error}</div>}
        
        {logs.map((log, index) => (
          <div key={index} style={{ whiteSpace: 'pre-wrap', marginBottom: '0.25rem' }}>
            {log}
          </div>
        ))}
      </div>
    </div>
  );
};

export default TradingLog;
