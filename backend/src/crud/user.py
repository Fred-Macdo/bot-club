from pymongo.database import Database
from bson import ObjectId
from typing import Optional

from ..models.user import UserCreate, UserInDB, UserUpdate
from ..utils.security import get_password_hash
from ..utils.db_executor import run_db_operation


async def get_user_by_email(db: Database, email: str) -> Optional[UserInDB]:
    user = await run_db_operation(db.user.find_one, {"email": email})
    if user:
        return UserInDB(**user)
    return None


async def get_user_by_username(db: Database, username: str) -> Optional[UserInDB]:
    user = await run_db_operation(db.user.find_one, {"userName": username})
    if user:
        return UserInDB(**user)
    return None


async def get_user_by_mongodb_id(db: Database, user_id: str) -> Optional[UserInDB]:
    user = await run_db_operation(db.user.find_one, {"_id": ObjectId(user_id)})
    if user:
        return UserInDB(**user)
    return None


async def create_user(db: Database, user: UserCreate) -> UserInDB:
    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump(exclude={"password"})
    user_data["hashed_password"] = hashed_password

    result = await run_db_operation(db.user.insert_one, user_data)

    created_user = await run_db_operation(db.user.find_one, {"_id": result.inserted_id})
    return UserInDB(**created_user)


async def update_user(
    db: Database, user_id: str, user_update: UserUpdate
) -> Optional[UserInDB]:
    update_data = {k: v for k, v in user_update.model_dump().items() if v is not None}

    if not update_data:
        return await get_user_by_mongodb_id(db, user_id)

    await run_db_operation(
        db.user.update_one, {"_id": ObjectId(user_id)}, {"$set": update_data}
    )

    updated_user = await get_user_by_mongodb_id(db, user_id)
    return updated_user


async def create_user_from_google(db: Database, google_user_info: dict) -> UserInDB:
    """Create a new user from Google OAuth data"""
    try:
        # Generate a random password since user is using OAuth
        import secrets

        random_password = secrets.token_urlsafe(32)

        # Extract data from Google user info
        email = google_user_info.get("email")
        given_name = google_user_info.get("given_name", "")
        family_name = google_user_info.get("family_name", "")
        picture = google_user_info.get("picture")

        # Create username from email (before @)
        username = email.split("@")[0]

        # Check if username already exists, add number if needed
        existing_username = await get_user_by_username(db, username)
        if existing_username:
            import random

            username = f"{username}{random.randint(1000, 9999)}"

        user_dict = {
            "userName": username,
            "email": email,
            "firstName": given_name or "User",
            "lastName": family_name or "Name",
            "profileImage": picture,
            "timezone": "America/New_York",
            "role": "user",
            "isActive": True,
            "hashed_password": get_password_hash(random_password),
            "phone": None,
            "addressLine1": None,
            "addressLine2": None,
            "city": None,
            "state": None,
            "zipCode": None,
            "bio": None,
        }

        result = await run_db_operation(db.user.insert_one, user_dict)
        created_user = await run_db_operation(
            db.user.find_one, {"_id": result.inserted_id}
        )

        if created_user:
            return UserInDB(**created_user)
        else:
            raise Exception("Failed to retrieve created user")
    except Exception as e:
        print(f"Error creating user from Google: {e}")
        raise
