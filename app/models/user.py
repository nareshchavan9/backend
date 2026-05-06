from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from enum import Enum

class UserRole(str, Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: UserRole = UserRole.PATIENT
    age: Optional[int] = None
    gender: Optional[str] = None
    medical_history: Optional[str] = None
    profile_image: Optional[str] = None
    lifestyle_notes: List[dict] = []
    two_factor_enabled: bool = False

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class OTPVerify(BaseModel):
    email: EmailStr
    otp: str

class UserResponse(UserBase):
    id: str = Field(alias="_id")

    class Config:
        populate_by_name = True

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    name: str
    profile_image: Optional[str] = None
    email: Optional[str] = None
    two_factor_enabled: bool = False
