from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel
from pymongo.database import Database
from ..dependencies import get_db, get_current_user_from_token
from ..models.user import UserInDB, UserUpdate, UserProfile
from ..crud.user import update_user, get_user_by_mongodb_id
from ..utils.security import verify_password
from ..utils.db_executor import run_db_operation
from .auth import _clear_auth_cookie
from bson import ObjectId

router = APIRouter()


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    current_user: UserInDB = Depends(get_current_user_from_token),
):
    """Get current user's profile"""
    return UserProfile(**current_user.model_dump())


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    user_update: UserUpdate,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """Update current user's profile"""
    # Convert to dict and exclude None values
    update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}

    updated_user = await update_user(db, str(current_user.id), update_data)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return UserProfile(**updated_user.model_dump())


@router.get("/profile/{user_id}", response_model=UserProfile)
async def get_user_profile(
    user_id: str,
    db: Database = Depends(get_db),
    current_user: UserInDB = Depends(get_current_user_from_token),
):
    """Get any user's profile by ID (for viewing other users)"""
    try:
        user = await get_user_by_mongodb_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return UserProfile(**user.model_dump())
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID"
        )


class DeleteAccountRequest(BaseModel):
    password: str


@router.delete("/me")
async def delete_account(
    body: DeleteAccountRequest,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db),
):
    """Permanently delete the current user's account and all associated data."""
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    user_id = str(current_user.id)

    # Gather backtest IDs so we can clean up backtest_executions
    backtest_docs = await run_db_operation(db.backtests.find, {"user_id": user_id})
    backtest_ids = [doc["backtest_id"] for doc in backtest_docs if "backtest_id" in doc]

    if backtest_ids:
        await run_db_operation(
            db.backtest_executions.delete_many, {"backtest_id": {"$in": backtest_ids}}
        )

    # Delete all user-owned data
    for collection_name, query in [
        ("backtests", {"user_id": user_id}),
        ("trading_sessions", {"user_id": user_id}),
        ("strategy_portfolios", {"user_id": user_id}),
        ("strategy", {"user_id": user_id}),
        ("user_config", {"user_id": user_id}),
    ]:
        await run_db_operation(getattr(db, collection_name).delete_many, query)

    # Delete the user document itself
    await run_db_operation(db.user.delete_one, {"_id": ObjectId(user_id)})

    # Clear auth cookie
    response = Response(status_code=200)
    response.body = b'{"message":"Account deleted"}'
    response.media_type = "application/json"
    _clear_auth_cookie(response)
    return response
