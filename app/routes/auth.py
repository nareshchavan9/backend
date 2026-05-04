from fastapi import APIRouter, Depends, HTTPException, status
from app.models.user import UserCreate, UserLogin, Token, UserResponse
from app.database.db import get_database
from app.utils.auth_utils import get_password_hash, verify_password, create_access_token
from datetime import timedelta

router = APIRouter()

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate):
    db = get_database()
    existing_user = await db["users"].find_one({"email": user.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user_dict = user.dict()
    user_dict["password_hash"] = get_password_hash(user_dict.pop("password"))
    
    new_user = await db["users"].insert_one(user_dict)
    created_user = await db["users"].find_one({"_id": new_user.inserted_id})
    created_user["_id"] = str(created_user["_id"])
    return created_user

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    db = get_database()
    user = await db["users"].find_one({"email": user_data.email})
    
    if not user or not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user["role"],
        "name": user["name"]
    }

@router.post("/reset-password")
async def reset_password(data: dict):
    email = data.get("email")
    new_password = data.get("password")
    
    if not email or not new_password:
        raise HTTPException(status_code=400, detail="Email and new password are required")
        
    db = get_database()
    user = await db["users"].find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    hashed_password = get_password_hash(new_password)
    await db["users"].update_one(
        {"email": email},
        {"$set": {"password_hash": hashed_password}}
    )
    
    return {"message": "Password reset successful"}
