import React from 'react';
import { Paper, Typography, Box, Chip } from '@mui/material';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { useDeployedStrategy } from '../../../context/DeployedStrategyContext';

const DeployedStrategies = ({ isPaperMode }) => {
  const { modeStates } = useDeployedStrategy();
  const paperState = modeStates?.paper;
  const liveState = modeStates?.live;

  const activeStrategies = [];
  if (paperState?.isDeployed && paperState.deployedStrategy) {
    activeStrategies.push({ mode: 'Paper', name: paperState.deployedStrategy.name || 'Unnamed Strategy' });
  }
  if (liveState?.isDeployed && liveState.deployedStrategy) {
    activeStrategies.push({ mode: 'Live', name: liveState.deployedStrategy.name || 'Unnamed Strategy' });
  }

  return (
    <Paper sx={{ p: 2, borderRadius: 2, mb: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: activeStrategies.length > 0 ? 1.5 : 0 }}>
        <Box>
          <Typography variant="h6">Deployed Strategies</Typography>
          <Typography variant="body2" color="text.secondary">
            {isPaperMode ? 'Paper Trading Performance' : 'Live Trading Performance'}
          </Typography>
        </Box>
        {activeStrategies.length > 0 && (
          <Chip
            label={`${activeStrategies.length} Active`}
            color="success"
            size="small"
            variant="outlined"
          />
        )}
      </Box>
      {activeStrategies.length === 0 ? (
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic', mt: 1 }}>
          No strategies currently deployed
        </Typography>
      ) : (
        activeStrategies.map((s, i) => (
          <Box
            key={i}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              py: 0.75,
              borderTop: i > 0 ? 1 : 0,
              borderColor: 'divider',
            }}
          >
            <PlayArrowIcon color="success" sx={{ fontSize: 18 }} />
            <Typography variant="body2" sx={{ fontWeight: 'bold', flexGrow: 1 }}>
              {s.name}
            </Typography>
            <Chip
              label={s.mode}
              size="small"
              color={s.mode === 'Live' ? 'error' : 'info'}
              sx={{ height: 20, fontSize: '0.7rem' }}
            />
          </Box>
        ))
      )}
    </Paper>
  );
};

export default DeployedStrategies;
