import os
import uuid
import io
import asyncio
import time
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
    Optimized Gemini check with thumbnailing and concurrency.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: return True
        
    try:
        # Resize to thumbnail to minimize upload time
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((384, 384)) 
        thumb_io = io.BytesIO()
        img.save(thumb_io, format='JPEG', quality=80)
        thumb_bytes = thumb_io.getvalue()
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = "Is this image a valid ECG plot? Answer YES or NO."
        
        # 5 second timeout for AI check specifically
        response_task = model.generate_content_async([prompt, Image.open(io.BytesIO(thumb_bytes))])
        response = await asyncio.wait_for(response_task, timeout=5.0)
        
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
    start_time = time.time()
    print(f"DIAGNOSTIC START: {datetime.utcnow()}")
    
    # 1. Start AI validation task (Non-blocking)
    validation_task = asyncio.create_task(validate_ecg_with_gemini(image_bytes))
    
    db = get_database()
    from bson import ObjectId

    # 2. Parallelize Data Fetching
    p_user_task = db["users"].find_one({"_id": ObjectId(user_id)}, {"name": 1, "role": 1})
    d_user_task = db["users"].find_one({"_id": ObjectId(doctor_id)}, {"name": 1}) if doctor_id else None
    
    # 3. RUN MODEL INFERENCE IN THREAD (To prevent blocking the event loop)
    # This is critical to keep the total time low.
    processed_img = preprocess_image(image_bytes)
    prediction_probs = await asyncio.to_thread(model_loader.predict, processed_img)
    label, confidence, breakdown = get_class_label(prediction_probs)
    
    # Process metadata after inference
    p_user = await p_user_task
    patient_name = p_user["name"] if p_user else "Unknown Patient"
    doctor_name = "Self-Tested"
    if p_user and p_user.get("role") in ["doctor", "admin"]: doctor_name = f"Dr. {p_user['name']}"
    if d_user_task:
        d_user = await d_user_task
        if d_user: doctor_name = f"Dr. {d_user['name']}"

    # Logic for abnormal detection
    normal_item = next((item for item in breakdown if "normal" in item["label"].lower()), None)
    normal_percentage = normal_item["percentage"] if normal_item else 0
    total_risk = sum([item["percentage"] for item in breakdown if "normal" not in item["label"].lower()])
    
    if normal_percentage < 90.0:
        abnormal_types = [item["label"] for item in breakdown if "normal" not in item["label"].lower() and item["percentage"] > 2.0]
        label = f"Abnormal ({', '.join(abnormal_types[:3])})" if abnormal_types else "Abnormal Heart Rhythm"
        confidence = total_risk / 100.0

    # 4. Wait for AI Validation (Already running for several seconds now)
    try:
        is_valid = await validation_task
    except:
        is_valid = True # Default to valid on failure
        
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid input: Image does not appear to be an ECG plot.")

    # 5. Local File Operation
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
    
    end_time = time.time()
    print(f"DIAGNOSTIC COMPLETE: {end_time - start_time:.2f}s total")
    
    return {
        "id": str(result.inserted_id), "prediction": label, "confidence": confidence, 
        "breakdown": breakdown, "timestamp": prediction_record["timestamp"], "notes": notes,
        "patient_name": patient_name, "doctor_name": doctor_name
    }
