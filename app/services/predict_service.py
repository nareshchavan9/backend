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
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: return True
        
    try:
        genai.configure(api_key=api_key)
        # Use the specific lite model which we know exists and is fast
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        img = Image.open(io.BytesIO(image_bytes))
        
        prompt = "Is this image an ECG/EKG plot? Answer only YES or NO."
        response = await model.generate_content_async([prompt, img])
        
        if not response.candidates: return True
        result_text = response.text.strip().upper()
        if "NO" in result_text and "YES" not in result_text: return False
        return True
    except Exception as e:
        print(f"DEBUG: Gemini Validation Skip: {e}")
        return True

async def background_cloud_upload(prediction_id: str, image_bytes: bytes):
    """
    Uploads to Cloudinary in the background and updates the database record.
    """
    try:
        cloud_url = upload_image_to_cloud(image_bytes)
        if cloud_url:
            db = get_database()
            from bson import ObjectId
            await db["predictions"].update_one(
                {"_id": ObjectId(prediction_id)},
                {"$set": {"image_path": cloud_url}}
            )
            print(f"Background Upload Complete for {prediction_id}: {cloud_url}")
    except Exception as e:
        print(f"Background Upload Failed: {e}")

async def run_prediction(image_bytes: bytes, user_id: str, filename: str, notes: str = "", doctor_id: str = None, background_tasks: BackgroundTasks = None):
    # 1. Start Gemini Validation and Model Inference IN PARALLEL
    # This shaves off 3-5 seconds immediately
    validation_task = asyncio.create_task(validate_ecg_with_gemini(image_bytes))
    
    # Preprocess and Infer
    processed_img = preprocess_image(image_bytes)
    prediction_probs = model_loader.predict(processed_img)
    top_label, top_confidence, breakdown = get_class_label(prediction_probs)
    
    # User Logic for Abnormal detection
    normal_item = next((item for item in breakdown if "normal" in item["label"].lower()), None)
    normal_percentage = normal_item["percentage"] if normal_item else 0
    total_risk = sum([item["percentage"] for item in breakdown if "normal" not in item["label"].lower()])
    
    if normal_percentage >= 90.0:
        label = "Normal Beat"
        confidence = top_confidence
    else:
        abnormal_types = [item["label"] for item in breakdown if "normal" not in item["label"].lower() and item["percentage"] > 2.0]
        label = f"Abnormal ({', '.join(abnormal_types[:3])})" if abnormal_types else "Abnormal Heart Rhythm"
        confidence = total_risk / 100.0

    # Wait for validation to finish
    is_valid = await validation_task
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid input: Image does not appear to be an ECG plot.")

    # 2. SPEED OPTIMIZATION: Save locally first, Cloudinary later in background
    upload_dir = os.getenv("UPLOAD_DIR", "uploads")
    if not os.path.exists(upload_dir): os.makedirs(upload_dir)
    
    file_id = str(uuid.uuid4())
    extension = filename.split(".")[-1]
    save_filename = f"{file_id}.{extension}"
    local_path = os.path.join(upload_dir, save_filename)
    
    with open(local_path, "wb") as f:
        f.write(image_bytes)
    
    # Fetch names for denormalization
    db = get_database()
    from bson import ObjectId
    patient_name = "Unknown Patient"
    doctor_name = "Unknown Doctor"
    try:
        p_user = await db["users"].find_one({"_id": ObjectId(user_id)}, {"name": 1, "role": 1})
        if p_user: 
            patient_name = p_user["name"]
            if p_user.get("role") in ["doctor", "admin"]: doctor_name = f"Dr. {p_user['name']}"
        if doctor_id:
            d_user = await db["users"].find_one({"_id": ObjectId(doctor_id)}, {"name": 1})
            if d_user: doctor_name = f"Dr. {d_user['name']}"
    except: pass

    # Save to database with local path initially
    prediction_record = {
        "user_id": user_id,
        "doctor_id": doctor_id,
        "image_path": local_path, 
        "prediction": label,
        "confidence": confidence,
        "breakdown": breakdown,
        "timestamp": datetime.utcnow(),
        "notes": notes,
        "patient_name": patient_name,
        "doctor_name": doctor_name
    }
    
    result = await db["predictions"].insert_one(prediction_record)
    pred_id = str(result.inserted_id)

    # 3. Queue the Cloudinary upload in the background
    if background_tasks:
        background_tasks.add_task(background_cloud_upload, pred_id, image_bytes)
    
    return {
        "id": pred_id,
        "prediction": label,
        "confidence": confidence,
        "breakdown": breakdown,
        "timestamp": prediction_record["timestamp"],
        "notes": notes,
        "patient_name": patient_name,
        "doctor_name": doctor_name
    }
