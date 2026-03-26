import React, { useRef, useEffect } from 'react';
import { useDeployedStrategy } from '../../context/DeployedStrategyContext';

// Helper to format the timestamp
const formatTime = (timestamp) => {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', { 
    hour12: false, 
    hour: '2-digit', 
    minute: '2-digit', 
    second: '2-digit' 
  });
};

const TradingLog = () => {
  const { logs, socketStatus, socketError } = useDeployedStrategy();
  const bottomRef = useRef(null);

  // Auto-scroll to bottom nicely when new logs arrive
  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  // Determine color based on log level
  const getLogStyle = (level) => {
    switch (level?.toUpperCase()) {
      case 'ERROR': return { color: '#fc8181' }; // Red
      case 'WARNING': return { color: '#f6e05e' }; // Yellow
      case 'SUCCESS': return { color: '#68d391' }; // Green
      case 'INFO': 
      default: return { color: '#e2e8f0' }; // Gray/White
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-4 h-96 flex flex-col font-mono text-sm border border-gray-700">
      <div className="flex justify-between items-center mb-2 pb-2 border-b border-gray-600">
        <h3 className="text-gray-300 font-semibold">Live Strategy Logs</h3>
        <div className="flex items-center gap-2">
           <span className="text-xs text-gray-400">Status:</span>
           <span 
             className={`px-2 py-0.5 rounded text-xs font-bold ${
               socketStatus === 'connected' ? 'bg-green-900 text-green-300' : 
               socketStatus === 'error' ? 'bg-red-900 text-red-300' : 'bg-gray-700 text-gray-300'
             }`}
           >
             {socketStatus.toUpperCase()}
           </span>
        </div>
      </div>
      
      {socketError && (
        <div className="bg-red-900/50 p-2 mb-2 rounded text-red-200 border border-red-800 text-xs">
          <strong>Connection Error:</strong> {socketError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-1 space-y-1 scrollbar-thin scrollbar-thumb-gray-600">
        {/* We use flex-col-reverse in the parent or map normally. 
            Standard logs usually go Top=Oldest, Bottom=Newest. 
            If your API sends [newest, ...old], we map normally but the container scroll handles it.
        */}
        {[...logs].reverse().map((log, index) => {
          // Handle both object logs and legacy string logs
          const isObject = typeof log === 'object' && log !== null;
          const message = isObject ? log.message : log;
          const level = isObject ? log.level : 'INFO';
          const time = isObject ? log.timestamp : null;
          const data = isObject ? log.data : null;

          return (
            <div key={index} className="flex gap-2 hover:bg-white/5 p-0.5 rounded flex-wrap">
              <div className="flex gap-2 w-full">
                  <span className="text-gray-500 shrink-0 select-none" style={{ minWidth: '65px' }}>
                    [{time ? formatTime(time) : '--:--:--'}]
                  </span>
                  <span className="font-bold shrink-0" style={{ minWidth: '60px', ...getLogStyle(level) }}>
                    {level}
                  </span>
                  <span style={{ color: '#cbd5e0', whiteSpace: 'pre-wrap', wordBreak: 'break-word', flex: 1 }}>
                    {message}
                  </span>
              </div>
              
              {/* Render Structured Data (Tables, etc) */}
              {data && data.type === 'dataframe' && Array.isArray(data.data) && (
                <div className="w-full pl-16 mt-1 overflow-x-auto">
                   <table className="w-full text-xs text-left border-collapse border border-gray-600 bg-gray-900/50">
                     <thead className="bg-gray-700 text-gray-200">
                       <tr>
                         {Object.keys(data.data[0] || {}).map(header => (
                           <th key={header} className="px-2 py-1 border border-gray-600 font-semibold">{header}</th>
                         ))}
                       </tr>
                     </thead>
                     <tbody>
                       {data.data.map((row, i) => (
                         <tr key={i} className="hover:bg-white/5 text-gray-300">
                            {Object.values(row).map((val, j) => (
                              <td key={j} className="px-2 py-1 border border-gray-600 font-mono">
                                {typeof val === 'number' ? Number(val).toFixed(4) : String(val)}
                              </td>
                            ))}
                         </tr>
                       ))}
                     </tbody>
                   </table>
                </div>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

export default TradingLog;
