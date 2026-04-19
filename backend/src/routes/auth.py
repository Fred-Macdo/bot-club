from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse, JSONResponse
from pymongo.database import Database
from jose import JWTError, jwt
from passlib.context import CryptContext
import httpx
import os
from bson import ObjectId

from pydantic import BaseModel, Field

from ..dependencies import get_db, get_current_user_from_token
from ..models.user import UserCreate, UserInDB, UserProfile, Token
from ..crud.user import create_user, get_user_by_email, get_user_by_username, create_user_from_google
from ..crud.strategy import get_strategies_by_user_id
from ..utils.security import verify_password, create_access_token, get_password_hash
from ..utils.db_executor import run_db_operation
from ..config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI

router = APIRouter()

_COOKIE_NAME = "access_token"
_COOKIE_MAX_AGE = 1800  # 30 minutes
_IS_PRODUCTION = os.getenv("NODE_ENV") == "production"


def _set_auth_cookie(response: Response, token: str):
    """Set httpOnly cookie with the JWT token."""
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_auth_cookie(response: Response):
    """Clear the auth cookie."""
    response.delete_cookie(
        key=_COOKIE_NAME,
        httponly=True,
        secure=_IS_PRODUCTION,
        samesite="lax",
        path="/",
    )

@router.post("/register", response_model=UserProfile)
async def register_user(
    user: UserCreate,
    db: Database = Depends(get_db)
):
    """Register a new user"""
    try:
        # Check if user already exists by email
        existing_user = await get_user_by_email(db, user.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Check if username already exists
        existing_username = await get_user_by_username(db, user.userName)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        
        # Create new user
        created_user = await create_user(db, user)
        
        # Create default strategies for the new user
        #await create_default_strategies_for_user(db, created_user.id)
        
        return UserProfile(**created_user.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Database = Depends(get_db)
):
    """Authenticate user and return access token"""
    try:        # Try to get user by username or email
        user = await get_user_by_username(db, form_data.username)
        if not user:
            user = await get_user_by_email(db, form_data.username)
        
        # Verify user exists and password is correct
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Check if user has default strategies, create them if not
        existing_strategies = await get_strategies_by_user_id(db, user.id)
        #await create_default_strategies_for_user(db, user.id)
        
        # Create access token
        access_token = create_access_token(data={"sub": str(user.id)})
        
        response = JSONResponse(content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": _COOKIE_MAX_AGE,
        })
        _set_auth_cookie(response, access_token)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.get("/google/login")
async def google_login(redirect_uri: str, state: str):
    """
    Redirect to Google OAuth consent screen
    
    Args:
        redirect_uri: The frontend callback URL
        state: CSRF protection state parameter
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured"
        )
    
    # Construct Google OAuth URL
    google_oauth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope=openid%20email%20profile&"
        f"state={state}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    
    return RedirectResponse(url=google_oauth_url)

@router.get("/google/callback")
async def google_callback(
    code: str,
    db: Database = Depends(get_db)
):
    """
    Handle Google OAuth callback and exchange code for token
    
    Args:
        code: Authorization code from Google
        db: Database connection
    
    Returns:
        Access token and user information
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google OAuth is not configured"
        )
    
    try:
        # Exchange authorization code for tokens
        async with httpx.AsyncClient() as client:
            # Get the redirect URI from config (env var)
            redirect_uri = GOOGLE_REDIRECT_URI
            
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
            )
            
            if token_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code for token: {token_response.text}"
                )
            
            token_data = token_response.json()
            
            # Get user info from Google
            user_info_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {token_data['access_token']}"}
            )
            
            if user_info_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get user info from Google"
                )
            
            user_info = user_info_response.json()
        
        # Find or create user in database
        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        user = await get_user_by_email(db, email)
        
        if not user:
            # Create new user from Google info
            user = await create_user_from_google(db, user_info)
            print(f"Created new user from Google OAuth: {email}")
        else:
            print(f"Existing user logged in via Google OAuth: {email}")
        
        # Generate JWT token for our app
        access_token = create_access_token(data={"sub": str(user.id)})
        
        response = JSONResponse(content={
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": _COOKIE_MAX_AGE,
            "user": UserProfile(**user.model_dump()).model_dump(mode='json'),
        })
        _set_auth_cookie(response, access_token)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Google OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Authentication failed: {str(e)}"
        )


@router.post("/logout")
async def logout():
    """Clear the auth cookie."""
    response = JSONResponse(content={"message": "Logged out"})
    _clear_auth_cookie(response)
    return response


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


@router.put("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )
    hashed = get_password_hash(body.new_password)
    await run_db_operation(
        db.user.update_one,
        {"_id": ObjectId(current_user.id)},
        {"$set": {"hashed_password": hashed}},
    )
    return {"message": "Password updated"}
