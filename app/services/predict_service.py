import os
import uuid
import io
from PIL import Image
from datetime import datetime
from fastapi import HTTPException
import google.generativeai as genai
from app.services.model_loader import model_loader
from app.services.preprocess import preprocess_image, get_class_label
from app.database.db import get_database

async def validate_ecg_with_gemini(image_bytes: bytes) -> bool:
    """
    Uses Gemini Vision to verify if the uploaded image is actually an ECG plot.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("DEBUG: No GOOGLE_API_KEY found, skipping Gemini validation.")
        return True
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        img = Image.open(io.BytesIO(image_bytes))
        
        prompt = "Is this an ECG/EKG (Electrocardiogram) heart rate plot? Answer only with 'YES' or 'NO'."
        
        # Use async version for better performance
        response = await model.generate_content_async([prompt, img])
        
        result_text = response.text.strip().upper()
        print(f"DEBUG: Gemini ECG Validation response: '{result_text}'")
        
        if "NO" in result_text:
            return False
        return True
    except Exception as e:
        print(f"DEBUG: Gemini Validation Error (Falling back to True): {e}")
        return True

async def run_prediction(image_bytes: bytes, user_id: str, filename: str, notes: str = "", doctor_id: str = None):
    # Validate with Gemini
    is_valid = await validate_ecg_with_gemini(image_bytes)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid input: The uploaded image does not appear to be a valid ECG/EKG plot.")

    # Preprocess
    processed_img = preprocess_image(image_bytes)
    
    # Inference
    prediction_probs = model_loader.predict(processed_img)
    
    # Map to labels
    top_label, top_confidence, breakdown = get_class_label(prediction_probs)
    
    # User Requirement: 
    # 1. If Normal Beat > 90% -> Result is "Normal"
    # 2. Otherwise -> Result is "Abnormal" + List of detected abnormal beat types
    # 3. If Abnormal, the confidence score must be the TOTAL abnormal risk, not the top class score.
    
    normal_item = next((item for item in breakdown if "normal" in item["label"].lower()), None)
    normal_percentage = normal_item["percentage"] if normal_item else 0
    total_risk = sum([item["percentage"] for item in breakdown if "normal" not in item["label"].lower()])
    
    if normal_percentage >= 90.0:
        label = "Normal Beat"
        confidence = top_confidence # Use the top class confidence for normal results
    else:
        # Identify all significant abnormal beats (e.g., > 2% probability)
        abnormal_types = [
            item["label"] for item in breakdown 
            if "normal" not in item["label"].lower() and item["percentage"] > 2.0
        ]
        
        if abnormal_types:
            label = f"Abnormal ({', '.join(abnormal_types[:3])})"
        else:
            label = "Abnormal Heart Rhythm"
        
        # Override confidence to be the TOTAL risk percentage (decimal form)
        confidence = total_risk / 100.0
    
    # 4. Upload to Cloud (Cloudinary) or Save Locally
    # We prioritize cloud storage for production/hosting
    from app.services.cloudinary_service import upload_image_to_cloud
    
    cloud_url = upload_image_to_cloud(image_bytes)
    
    if cloud_url:
        save_path = cloud_url
        print(f"Image uploaded to Cloudinary: {cloud_url}")
    else:
        # Fallback to local storage if cloud fails
        upload_dir = os.getenv("UPLOAD_DIR", "uploads")
        file_id = str(uuid.uuid4())
        extension = filename.split(".")[-1]
        save_filename = f"{file_id}.{extension}"
        save_path = os.path.join(upload_dir, save_filename)
        
        with open(save_path, "wb") as f:
            f.write(image_bytes)
        print(f"Cloud upload failed. Saved locally to: {save_path}")
    
    # Save to database
    db = get_database()
    prediction_record = {
        "user_id": user_id,
        "doctor_id": doctor_id,
        "image_path": save_path, # This will now be a URL if cloud upload succeeded
        "prediction": label,
        "confidence": confidence,
        "breakdown": breakdown,
        "timestamp": datetime.utcnow(),
        "notes": notes
    }
    
    result = await db["predictions"].insert_one(prediction_record)
    
    return {
        "id": str(result.inserted_id),
        "prediction": label,
        "confidence": confidence,
        "breakdown": breakdown,
        "timestamp": prediction_record["timestamp"],
        "notes": notes
    }
