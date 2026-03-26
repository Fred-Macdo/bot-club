# Google OAuth2 Setup Guide

## Environment Variables Configuration

Create a `.env` file in the `backend` directory with the following variables:

```env
# MongoDB Configuration
MONGO_URL=mongodb://mongo:27017/
MONGO_DB_NAME=bot_club_db

# Backend Services
BACKEND_SERVICES_URL=http://backend_services:8001

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID=448814138980-46iokl7tmoa23n4t8kkugn5hpn7sa8d1.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback

# JWT Secret Key (generate a secure random string for production)
SECRET_KEY=your-secret-key-here-change-in-production

# Redis Configuration (if needed)
REDIS_URL=redis://redis:6379
```

## Google Cloud Console Setup

### Update Authorized Redirect URIs

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select project: **bot-club-alpha**
3. Navigate to **APIs & Services** → **Credentials**
4. Click on your OAuth 2.0 Client ID
5. Under **Authorized redirect URIs**, add:
   - Development: `http://localhost:3000/auth/google/callback`
   - Production: `https://yourdomain.com/auth/google/callback`
6. Click **Save**

### Current Configuration

- **Client ID**: `448814138980-46iokl7tmoa23n4t8kkugn5hpn7sa8d1.apps.googleusercontent.com`
- **Project**: bot-club-alpha
- **Current Redirect URI**: ~~http://localhost:3000/getting-started~~ (needs to be changed)
- **Required Redirect URI**: `http://localhost:3000/auth/google/callback` ✅

## API Endpoints Created

### 1. `/api/auth/google/login`
- **Method**: GET
- **Description**: Redirects user to Google OAuth consent screen
- **Parameters**:
  - `redirect_uri`: Frontend callback URL
  - `state`: CSRF protection token

### 2. `/api/auth/google/callback`
- **Method**: GET
- **Description**: Handles OAuth callback from Google
- **Parameters**:
  - `code`: Authorization code from Google
- **Returns**:
  ```json
  {
    "access_token": "jwt-token",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": "user-id",
      "email": "user@example.com",
      "firstName": "John",
      "lastName": "Doe",
      ...
    }
  }
  ```

## How It Works

1. User clicks "Continue with Google" button on login page
2. Frontend redirects to `/api/auth/google/login` with state parameter
3. Backend redirects to Google OAuth consent screen
4. User authenticates with Google
5. Google redirects back to frontend at `/auth/google/callback?code=...`
6. Frontend sends code to `/api/auth/google/callback`
7. Backend exchanges code for Google access token
8. Backend fetches user info from Google
9. Backend finds or creates user in database
10. Backend returns JWT token for app authentication
11. Frontend stores token and redirects to dashboard

## Security Features

- ✅ CSRF protection with state parameter
- ✅ Secure token exchange
- ✅ Email verification through Google
- ✅ Automatic user creation with random password
- ✅ JWT token generation for app authentication
- ✅ Username collision handling (adds random numbers if needed)

## Testing

1. Start the backend server
2. Start the frontend server
3. Navigate to login page
4. Click "Continue with Google"
5. Authenticate with your Google account
6. Verify redirect to dashboard

## Troubleshooting

### Error: "redirect_uri_mismatch"
- Make sure the redirect URI in Google Console matches exactly: `http://localhost:3000/auth/google/callback`

### Error: "Google OAuth is not configured"
- Check that environment variables are set in `.env` file
- Restart the backend server after adding environment variables

### Error: "Failed to exchange code for token"
- Verify client ID and client secret are correct
- Check that the authorization code hasn't expired (codes are single-use)

### User created but login fails
- Check database connection
- Verify JWT secret key is set
- Check backend logs for detailed error messages


