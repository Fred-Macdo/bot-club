import React, { useState } from 'react';
import {
  Box,
  TextField,
  Button,
  Alert,
  Typography,
  Divider,
  Paper,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  Fade,
} from '@mui/material';
import { Lock as LockIcon, DeleteForever as DeleteIcon } from '@mui/icons-material';
import { authApi } from '../../api/Client';

const SecuritySettingsForm = () => {
  // Change password state
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  });
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordStatus, setPasswordStatus] = useState(null);

  // Delete account state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const handlePasswordChange = (e) => {
    setPasswordForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
    setPasswordStatus(null);
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();

    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordStatus({ type: 'error', message: 'New passwords do not match' });
      return;
    }
    if (passwordForm.newPassword.length < 6) {
      setPasswordStatus({ type: 'error', message: 'New password must be at least 6 characters' });
      return;
    }

    setPasswordLoading(true);
    try {
      await authApi.changePassword(passwordForm.currentPassword, passwordForm.newPassword);
      setPasswordStatus({ type: 'success', message: 'Password updated successfully' });
      setPasswordForm({ currentPassword: '', newPassword: '', confirmPassword: '' });
    } catch (err) {
      const msg = err?.detail || err?.message || 'Failed to change password';
      setPasswordStatus({ type: 'error', message: msg });
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await authApi.deleteAccount(deletePassword);
      // Account is gone — log out and redirect
      authApi.logout();
    } catch (err) {
      const msg = err?.detail || err?.message || 'Failed to delete account';
      setDeleteError(msg);
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <Box>
      {/* Change Password Section */}
      <Typography variant="h6" gutterBottom>
        <LockIcon fontSize="small" sx={{ mr: 1, verticalAlign: 'middle' }} />
        Change Password
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Enter your current password and choose a new one.
      </Typography>

      {passwordStatus && (
        <Fade in>
          <Alert severity={passwordStatus.type} sx={{ mb: 2 }}>
            {passwordStatus.message}
          </Alert>
        </Fade>
      )}

      <Box component="form" onSubmit={handleChangePassword} sx={{ maxWidth: 400 }}>
        <TextField
          fullWidth
          label="Current Password"
          name="currentPassword"
          type="password"
          value={passwordForm.currentPassword}
          onChange={handlePasswordChange}
          required
          sx={{ mb: 2 }}
        />
        <TextField
          fullWidth
          label="New Password"
          name="newPassword"
          type="password"
          value={passwordForm.newPassword}
          onChange={handlePasswordChange}
          required
          inputProps={{ minLength: 6 }}
          helperText="Minimum 6 characters"
          sx={{ mb: 2 }}
        />
        <TextField
          fullWidth
          label="Confirm New Password"
          name="confirmPassword"
          type="password"
          value={passwordForm.confirmPassword}
          onChange={handlePasswordChange}
          required
          sx={{ mb: 2 }}
        />
        <Button
          type="submit"
          variant="contained"
          disabled={passwordLoading || !passwordForm.currentPassword || !passwordForm.newPassword || !passwordForm.confirmPassword}
          startIcon={passwordLoading ? <CircularProgress size={18} /> : <LockIcon />}
        >
          {passwordLoading ? 'Updating…' : 'Update Password'}
        </Button>
      </Box>

      {/* Danger Zone */}
      <Divider sx={{ my: 5 }} />

      <Paper
        variant="outlined"
        sx={{
          p: 3,
          borderColor: 'error.main',
          borderWidth: 2,
        }}
      >
        <Typography variant="h6" color="error" gutterBottom>
          <DeleteIcon fontSize="small" sx={{ mr: 1, verticalAlign: 'middle' }} />
          Delete Account
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Permanently delete your account and all associated data including strategies, backtests,
          trading sessions, and API configurations. This action cannot be undone.
        </Typography>
        <Button
          variant="outlined"
          color="error"
          onClick={() => setDeleteDialogOpen(true)}
        >
          Delete My Account
        </Button>
      </Paper>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => { setDeleteDialogOpen(false); setDeleteError(null); setDeletePassword(''); }}>
        <DialogTitle sx={{ color: 'error.main' }}>Confirm Account Deletion</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            This will permanently delete your account and all your data. Enter your password to confirm.
          </DialogContentText>
          {deleteError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {deleteError}
            </Alert>
          )}
          <TextField
            autoFocus
            fullWidth
            label="Password"
            type="password"
            value={deletePassword}
            onChange={(e) => { setDeletePassword(e.target.value); setDeleteError(null); }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => { setDeleteDialogOpen(false); setDeleteError(null); setDeletePassword(''); }}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={deleteLoading || !deletePassword}
            onClick={handleDeleteAccount}
            startIcon={deleteLoading ? <CircularProgress size={18} /> : <DeleteIcon />}
          >
            {deleteLoading ? 'Deleting…' : 'Delete Account'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default SecuritySettingsForm;
