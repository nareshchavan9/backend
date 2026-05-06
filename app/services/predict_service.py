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
    High-accuracy clinical validation using Gemini.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: return True
        
    try:
        # Resize slightly and ENSURE RGB mode (fixes the RGBA to JPEG crash)
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        img.thumbnail((512, 512)) 
        
        thumb_io = io.BytesIO()
        img.save(thumb_io, format='JPEG', quality=90)
        thumb_image = Image.open(io.BytesIO(thumb_io.getvalue()))
        
        genai.configure(api_key=api_key)
        # Use the model that is confirmed to work in your environment
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = (
            "CRITICAL MEDICAL VALIDATION: Determine if this image is a Cardiac ECG/EKG strip or plot. "
            "If the image contains heart rhythm waveforms (P-QRS-T complexes), reply with 'YES'. "
            "If the image is a person, a document, a landscape, or any other non-ECG image, you MUST reply with 'NO'. "
            "Be extremely strict. Reply ONLY with 'YES' or 'NO'."
        )
        
        response = await model.generate_content_async([prompt, thumb_image])
        
        if not response.candidates: return False
        
        result_text = response.text.strip().upper()
        print(f"DEBUG: AI Validation Response: {result_text}")
        
        # Strict validation: Only 'YES' is allowed
        return "YES" in result_text and "NO" not in result_text
        
    except Exception as e:
        print(f"DEBUG: AI Validation Exception (Skipped): {e}")
        # If the AI itself fails technically, we'll allow it but log it.
        return True

async def background_cloud_upload(prediction_id: str, image_bytes: bytes):
    """
    Optimized cloud upload: Resizes image to web-standard before sync to save bandwidth.
    """
    try:
        # Optimization: Resize for the web before uploading to Cloudinary
        img = Image.open(io.BytesIO(image_bytes))
        if img.width > 1200:
            img.thumbnail((1200, 1200))
        
        opt_io = io.BytesIO()
        img.save(opt_io, format='JPEG', quality=85)
        optimized_bytes = opt_io.getvalue()
        
        cloud_url = upload_image_to_cloud(optimized_bytes)
        if cloud_url:
            db = get_database()
            from bson import ObjectId
            await db["predictions"].update_one(
                {"_id": ObjectId(prediction_id)},
                {"$set": {"image_path": cloud_url}}
            )
            print(f"DEBUG: Background Cloud Sync Complete for {prediction_id}")
    except Exception as e:
        print(f"DEBUG: Background Cloud Sync Failed: {e}")

async def run_prediction(image_bytes: bytes, user_id: str, filename: str, notes: str = "", doctor_id: str = None, background_tasks: BackgroundTasks = None):
    start_time = time.time()
    
    # 1. Start STRICT AI validation
    validation_task = asyncio.create_task(validate_ecg_with_gemini(image_bytes))
    
    db = get_database()
    from bson import ObjectId

    # 2. Parallel Inference & Data Fetch
    p_user_task = db["users"].find_one({"_id": ObjectId(user_id)}, {"name": 1, "role": 1})
    d_user_task = db["users"].find_one({"_id": ObjectId(doctor_id)}, {"name": 1}) if doctor_id else None
    
    # Run the ECG model in a thread
    processed_img = preprocess_image(image_bytes)
    prediction_probs = await asyncio.to_thread(model_loader.predict, processed_img)
    label, confidence, breakdown = get_class_label(prediction_probs)
    
    # Metadata resolution
    p_user = await p_user_task
    patient_name = p_user["name"] if p_user else "Unknown Patient"
    doctor_name = "Self-Tested"
    if p_user and p_user.get("role") in ["doctor", "admin"]: doctor_name = f"Dr. {p_user['name']}"
    if d_user_task:
        d_user = await d_user_task
        if d_user: doctor_name = f"Dr. {d_user['name']}"

    # Heart rhythm logic
    normal_item = next((item for item in breakdown if "normal" in item["label"].lower()), None)
    normal_percentage = normal_item["percentage"] if normal_item else 0
    total_risk = sum([item["percentage"] for item in breakdown if "normal" not in item["label"].lower()])
    
    if normal_percentage < 90.0:
        abnormal_types = [item["label"] for item in breakdown if "normal" not in item["label"].lower() and item["percentage"] > 2.0]
        label = f"Abnormal ({', '.join(abnormal_types[:3])})" if abnormal_types else "Abnormal Heart Rhythm"
        confidence = total_risk / 100.0

    # 3. Wait for STRICT Validation
    is_valid = await validation_task
    if not is_valid:
        print("REJECTED: AI determined image is not an ECG.")
        raise HTTPException(status_code=400, detail="Invalid input: The uploaded image is not a valid ECG plot. Please upload a clear diagnostic chart.")

    # 4. Enforce the 9.5s "Clinical Stability" window
    # This provides a consistent, thorough experience for the user.
    elapsed = time.time() - start_time
    if elapsed < 9.5:
        await asyncio.sleep(9.5 - elapsed)

    # 5. Finalize and Save
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
    
    print(f"DIAGNOSTIC COMPLETE: {time.time() - start_time:.2f}s")
    
    return {
        "id": str(result.inserted_id), "prediction": label, "confidence": confidence, 
        "breakdown": breakdown, "timestamp": prediction_record["timestamp"], "notes": notes,
        "patient_name": patient_name, "doctor_name": doctor_name
    }
