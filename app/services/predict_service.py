import os
import uuid
import io
import asyncio
from PIL import Image
from datetime import datetime
from fastapi import HTTPException, BackgroundTasks
import google.generativeai as genai
from app.services.model_loader import model_loader
from app.services.preprocess import preprocess_image, get_class_label
from app.database.db import get_database
from app.services.cloudinary_service import upload_image_to_cloud

async def validate_ecg_with_gemini(image_bytes: bytes) -> bool:
    """
    Optimized Gemini check with a comfortable timeout for stability.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: return True
        
    try:
        # Resize slightly to help bandwidth but keep enough detail for 7s window
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((512, 512)) 
        
        thumb_io = io.BytesIO()
        img.save(thumb_io, format='JPEG', quality=85)
        thumb_bytes = thumb_io.getvalue()
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = "Analyze this image. Is it a valid ECG/EKG cardiac plot? Answer YES or NO."
        
        # Increased timeout to 8s to allow for the user's 6-7s preference
        response_task = model.generate_content_async([prompt, Image.open(io.BytesIO(thumb_bytes))])
        response = await asyncio.wait_for(response_task, timeout=8.0)
        
        if not response.candidates: return True
        result_text = response.text.strip().upper()
        return "NO" not in result_text or "YES" in result_text
    except Exception as e:
        print(f"DEBUG: AI Validation Step: {e}")
        return True

async def background_cloud_upload(prediction_id: str, image_bytes: bytes):
    try:
        cloud_url = upload_image_to_cloud(image_bytes)
        if cloud_url:
            db = get_database()
            from bson import ObjectId
            await db["predictions"].update_one(
                {"_id": ObjectId(prediction_id)},
                {"$set": {"image_path": cloud_url}}
            )
    except Exception as e:
        print(f"Background Upload Failed: {e}")

async def run_prediction(image_bytes: bytes, user_id: str, filename: str, notes: str = "", doctor_id: str = None, background_tasks: BackgroundTasks = None):
    # 1. Run AI validation with a slightly longer window
    validation_task = asyncio.create_task(validate_ecg_with_gemini(image_bytes))
    
    db = get_database()
    from bson import ObjectId

    # 2. Sequential Inference & Data Fetch for stability
    processed_img = preprocess_image(image_bytes)
    prediction_probs = model_loader.predict(processed_img)
    label, confidence, breakdown = get_class_label(prediction_probs)
    
    # User metadata fetching
    p_user = await db["users"].find_one({"_id": ObjectId(user_id)}, {"name": 1, "role": 1})
    patient_name = p_user["name"] if p_user else "Unknown Patient"
    doctor_name = "Self-Tested"
    if p_user and p_user.get("role") in ["doctor", "admin"]: doctor_name = f"Dr. {p_user['name']}"
    
    if doctor_id:
        d_user = await db["users"].find_one({"_id": ObjectId(doctor_id)}, {"name": 1})
        if d_user: doctor_name = f"Dr. {d_user['name']}"

    # Logic for abnormal detection
    normal_item = next((item for item in breakdown if "normal" in item["label"].lower()), None)
    normal_percentage = normal_item["percentage"] if normal_item else 0
    total_risk = sum([item["percentage"] for item in breakdown if "normal" not in item["label"].lower()])
    
    if normal_percentage < 90.0:
        abnormal_types = [item["label"] for item in breakdown if "normal" not in item["label"].lower() and item["percentage"] > 2.0]
        label = f"Abnormal ({', '.join(abnormal_types[:3])})" if abnormal_types else "Abnormal Heart Rhythm"
        confidence = total_risk / 100.0

    # 3. Finalize results after AI check (max 8s)
    is_valid = await validation_task
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid input: Image does not appear to be an ECG plot.")

    # Save local copy
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    if not os.path.exists(upload_dir): os.makedirs(upload_dir)
    local_path = os.path.join(upload_dir, f"{uuid.uuid4()}.{filename.split('.')[-1]}")
    with open(local_path, "wb") as f: f.write(image_bytes)
    
    prediction_record = {
        "user_id": user_id, "doctor_id": doctor_id, "image_path": local_path, 
        "prediction": label, "confidence": confidence, "breakdown": breakdown,
        "timestamp": datetime.utcnow(), "notes": notes, "patient_name": patient_name, "doctor_name": doctor_name
    }
    
    result = await db["predictions"].insert_one(prediction_record)
    if background_tasks: background_tasks.add_task(background_cloud_upload, str(result.inserted_id), image_bytes)
    
    return {
        "id": str(result.inserted_id), "prediction": label, "confidence": confidence, 
        "breakdown": breakdown, "timestamp": prediction_record["timestamp"], "notes": notes,
        "patient_name": patient_name, "doctor_name": doctor_name
    }
