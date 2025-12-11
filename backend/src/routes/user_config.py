from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo.database import Database
from bson import ObjectId
from datetime import datetime, timezone

from ..dependencies import get_db, get_current_user_from_token
from ..models.user import UserInDB
from ..models.user_config import (
    UserConfigBase,
    UserConfigCreate,
    UserConfigUpdate,
    UserConfigInDB,
    UserConfigResponse,
    ConfigEncryption
)
from ..utils.db_executor import run_db_operation

router = APIRouter()

@router.get("/", response_model=Optional[UserConfigResponse])
async def get_user_config(
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Get user configuration"""
    try:
        # Find user config by user_id
        config_doc = await run_db_operation(db.user_config.find_one, {"user_id": str(current_user.id)})
        
        if not config_doc:
            return None
            
        # Convert ObjectIds to strings for Pydantic
        config_doc["_id"] = str(config_doc["_id"])
        config_doc["user_id"] = str(config_doc["user_id"])
        
        # Decrypt sensitive values
        if config_doc.get("alpaca_paper_secret_key"):
            config_doc["alpaca_paper_secret_key"] = ConfigEncryption.decrypt_value(config_doc["alpaca_paper_secret_key"])
        if config_doc.get("alpaca_live_secret_key"):
            config_doc["alpaca_live_secret_key"] = ConfigEncryption.decrypt_value(config_doc["alpaca_live_secret_key"])
        if config_doc.get("polygon_secret_key"):
            config_doc["polygon_secret_key"] = ConfigEncryption.decrypt_value(config_doc["polygon_secret_key"])
        
        return UserConfigResponse(**config_doc)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving configuration: {str(e)}"
        )

@router.post("/alpaca")
async def save_alpaca_config(
    config_data: dict,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Save Alpaca configuration (paper or live)"""
    try:
        # Prepare update data
        update_data = {
            "updated_at": datetime.now(timezone.utc)
        }
        
        # Handle paper trading config
        if "alpaca_paper_api_key" in config_data:
            update_data["alpaca_paper_api_key"] = config_data["alpaca_paper_api_key"]
            if config_data.get("alpaca_paper_secret_key"):
                update_data["alpaca_paper_secret_key"] = ConfigEncryption.encrypt_value(
                    config_data["alpaca_paper_secret_key"]
                )
            if config_data.get("alpaca_paper_endpoint"):
                update_data["alpaca_paper_endpoint"] = config_data["alpaca_paper_endpoint"]
        
        # Handle live trading config
        if "alpaca_live_api_key" in config_data:
            update_data["alpaca_live_api_key"] = config_data["alpaca_live_api_key"]
            if config_data.get("alpaca_live_secret_key"):
                update_data["alpaca_live_secret_key"] = ConfigEncryption.encrypt_value(
                    config_data["alpaca_live_secret_key"]
                )
            if config_data.get("alpaca_live_endpoint"):
                update_data["alpaca_live_endpoint"] = config_data["alpaca_live_endpoint"]
        
        # Upsert the configuration to user_config collection
        result = await run_db_operation(
            db.user_config.update_one,
            {"user_id": str(current_user.id)},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "user_id": str(current_user.id),
                    "created_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        return {"message": "Alpaca configuration saved successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving Alpaca configuration: {str(e)}"
        )

@router.post("/polygon")
async def save_polygon_config(
    config_data: dict,
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Save Polygon configuration"""
    try:
        update_data = {
            "updated_at": datetime.now(timezone.utc)
        }
        
        if config_data.get("polygon_api_key_name"):
            update_data["polygon_api_key_name"] = config_data["polygon_api_key_name"]
        
        if config_data.get("polygon_secret_key"):
            update_data["polygon_secret_key"] = ConfigEncryption.encrypt_value(config_data["polygon_secret_key"])
        
        # Upsert the configuration
        result = await run_db_operation(
            db.user_config.update_one,
            {"user_id": str(current_user.id)},
            {
                "$set": update_data,
                "$setOnInsert": {
                    "user_id": str(current_user.id),
                    "created_at": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        return {"message": "Polygon configuration saved successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error saving Polygon configuration: {str(e)}"
        )

@router.delete("/alpaca")
async def delete_alpaca_config(
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Delete Alpaca configuration"""
    try:
        # Remove Alpaca-related fields
        result = await run_db_operation(
            db.user_config.update_one,
            {"user_id": str(current_user.id)},
            {
                "$unset": {
                    "alpaca_paper_api_key": "",
                    "alpaca_paper_secret_key": "",
                    "alpaca_paper_endpoint": "",
                    "alpaca_live_api_key": "",
                    "alpaca_live_secret_key": "",
                    "alpaca_live_endpoint": ""
                },
                "$set": {
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        return {"message": "Alpaca configuration deleted successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting Alpaca configuration: {str(e)}"
        )

@router.delete("/polygon")
async def delete_polygon_config(
    current_user: UserInDB = Depends(get_current_user_from_token),
    db: Database = Depends(get_db)
):
    """Delete Polygon configuration"""
    try:
        # Remove Polygon-related fields
        result = await run_db_operation(
            db.user_config.update_one,
            {"user_id": str(current_user.id)},
            {
                "$unset": {
                    "polygon_api_key_name": "",
                    "polygon_secret_key": ""
                },
                "$set": {
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        return {"message": "Polygon configuration deleted successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting Polygon configuration: {str(e)}"
        )
