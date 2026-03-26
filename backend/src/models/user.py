from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from ..utils.mongo_helpers import PyObjectId

class UserAddress(BaseModel):
    addressLine1: Optional[str] = Field(default=None, alias="line1")
    addressLine2: Optional[str] = Field(default=None, alias="line2")
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None

    class Config:
        validate_by_name = True

class UserBase(BaseModel):
    userName: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    firstName: str = Field(..., min_length=1, max_length=100)
    lastName: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = None
    addressLine1: Optional[str] = None
    addressLine2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    timezone: str = "America/New_York"
    bio: Optional[str] = None
    profileImage: Optional[str] = None
    role: str = Field(default="user")
    isActive: bool = Field(default=True, alias="is_active")

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    confirmPassword: Optional[str] = None  # For frontend validation but not stored

    @field_validator('confirmPassword')
    @classmethod
    def passwords_match(cls, v, values):
        if hasattr(values, 'data') and 'password' in values.data and v != values.data['password']:
            raise ValueError('Passwords do not match')
        return v

class UserUpdate(BaseModel):
    userName: Optional[str] = Field(None, min_length=3, max_length=50)
    firstName: Optional[str] = Field(None, min_length=1, max_length=100)
    lastName: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = None
    addressLine1: Optional[str] = None
    addressLine2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    timezone: Optional[str] = None
    bio: Optional[str] = None
    profileImage: Optional[str] = None

    class Config:
        validate_by_name = True

class UserInDB(UserBase):
    id: Optional[str] = Field(alias="_id", default=None)
    hashed_password: str
    createdAt: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    
    @field_validator('id', mode='before')
    @classmethod
    def validate_id(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v
    
    class Config:
        validate_by_name = True
        from_attributes = True
        arbitrary_types_allowed = True

class User(UserBase):
    id: str = Field(alias="_id")
    createdAt: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def validate_id(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v
    
    class Config:
        validate_by_name = True
        from_attributes = True
        arbitrary_types_allowed = True

class UserProfile(BaseModel):
    id: str = Field(alias="_id")
    userName: str
    email: EmailStr
    firstName: str
    lastName: str
    phone: Optional[str] = None
    addressLine1: Optional[str] = None
    addressLine2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipCode: Optional[str] = None
    timezone: str
    bio: Optional[str] = None
    profileImage: Optional[str] = None
    role: str
    isActive: bool
    createdAt: datetime
    
    @field_validator('id', mode='before')
    @classmethod
    def validate_id(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v
    
    class Config:
        validate_by_name = True
        from_attributes = True
        arbitrary_types_allowed = True

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: Optional[int] = None

class TokenData(BaseModel):
    username: Optional[str] = None
