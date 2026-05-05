from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from app.models.user import UserCreate, UserLogin, Token, UserResponse
from app.database.db import get_database
from app.utils.auth_utils import get_password_hash, verify_password, create_access_token
from app.middleware.auth_middleware import get_current_user
from app.services.email_service import send_otp_email
from app.services.cloudinary_service import upload_image_to_cloud
from datetime import timedelta, datetime
from typing import Optional, List
from bson import ObjectId
import random

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
    
    if user.get("is_2fa_enabled"):
        otp = str(random.randint(100000, 999999))
        # Store OTP in DB with 10 min expiry
        await db["otps"].update_one(
            {"email": user["email"]},
            {"$set": {"otp": otp, "expires_at": datetime.utcnow() + timedelta(minutes=10)}},
            upsert=True
        )
        send_otp_email(user["email"], otp)
        return {
            "access_token": "pending_2fa", 
            "token_type": "bearer",
            "role": user["role"],
            "name": user["name"],
            "email": user["email"]
        }

    access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user["role"],
        "name": user["name"],
        "profile_image": user.get("profile_image"),
        "email": user["email"]
    }

@router.post("/verify-otp", response_model=Token)
async def verify_otp(data: dict):
    email = data.get("email")
    otp = data.get("otp")
    
    db = get_database()
    otp_record = await db["otps"].find_one({"email": email})
    
    if not otp_record or otp_record["otp"] != otp:
        raise HTTPException(status_code=401, detail="Invalid verification code")
    
    if otp_record["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Verification code expired")
    
    # Delete OTP after use
    await db["otps"].delete_one({"email": email})
    
    user = await db["users"].find_one({"email": email})
    access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})
    
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "role": user["role"],
        "name": user["name"],
        "profile_image": user.get("profile_image"),
        "email": user["email"]
    }

@router.post("/toggle-2fa")
async def toggle_2fa(current_user: dict = Depends(get_current_user)):
    db = get_database()
    new_status = not current_user.get("is_2fa_enabled", False)
    await db["users"].update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": {"is_2fa_enabled": new_status}}
    )
    return {"is_2fa_enabled": new_status}

@router.post("/lifestyle-notes")
async def add_lifestyle_note(note: dict, current_user: dict = Depends(get_current_user)):
    db = get_database()
    note["timestamp"] = datetime.utcnow().isoformat()
    await db["users"].update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$push": {"lifestyle_notes": note}}
    )
    return {"message": "Note added successfully"}

@router.delete("/lifestyle-notes/{timestamp}")
async def delete_lifestyle_note(timestamp: str, current_user: dict = Depends(get_current_user)):
    db = get_database()
    await db["users"].update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$pull": {"lifestyle_notes": {"timestamp": timestamp}}}
    )
    return {"message": "Note deleted successfully"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    current_user["_id"] = str(current_user["_id"])
    return current_user

@router.put("/profile", response_model=UserResponse)
async def update_profile(
    name: str = Form(...),
    email: str = Form(...),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    db = get_database()
    
    # Check if email is already taken by someone else
    if email != current_user["email"]:
        existing_user = await db["users"].find_one({"email": email})
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already taken")

    update_data = {
        "name": name,
        "email": email
    }

    if image:
        image_bytes = await image.read()
        image_url = upload_image_to_cloud(image_bytes, folder="profile_images")
        if image_url:
            update_data["profile_image"] = image_url

    await db["users"].update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": update_data}
    )
    
    updated_user = await db["users"].find_one({"_id": ObjectId(current_user["_id"])})
    updated_user["_id"] = str(updated_user["_id"])
    return updated_user

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
