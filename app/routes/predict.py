from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from typing import Optional
from app.middleware.auth_middleware import get_current_user, check_role
from app.services.predict_service import run_prediction
from app.database.db import get_database
from bson import ObjectId

router = APIRouter()

async def populate_history_metadata(history, db):
    for item in history:
        item["_id"] = str(item["_id"])
        
        # Populate Patient Name
        notes = item.get("notes", "")
        if notes and "Patient:" in notes:
            try:
                item["patient_name"] = notes.split("Patient:")[1].split("|")[0].strip()
            except:
                item["patient_name"] = "Clinical Patient"
        elif "user_id" in item:
            try:
                user = await db["users"].find_one({"_id": ObjectId(item["user_id"])}, {"name": 1})
                item["patient_name"] = user.get("name", "Unknown") if user else "Unknown"
            except:
                item["patient_name"] = "Unknown"
        else:
            item["patient_name"] = "Unknown"
            
        # Populate Doctor Name
        doctor_id = item.get("doctor_id")
        if doctor_id:
            try:
                doctor = await db["users"].find_one({"_id": ObjectId(doctor_id)}, {"name": 1})
                item["doctor_name"] = f"Dr. {doctor.get('name')}" if doctor else "Unknown Doctor"
            except:
                item["doctor_name"] = "Unknown Doctor"
        else:
            # Fallback/Check if the user_id itself is a doctor (for clinical patients)
            try:
                uid = item.get("user_id")
                if uid and ObjectId.is_valid(uid):
                    user = await db["users"].find_one({"_id": ObjectId(uid)})
                    if user and user.get("role") in ["doctor", "admin"]:
                        item["doctor_name"] = f"Dr. {user.get('name')}"
                    else:
                        item["doctor_name"] = "Self-Tested"
                else:
                    item["doctor_name"] = "System"
            except:
                item["doctor_name"] = "N/A"
    return history

@router.get("/all", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_all_predictions():
    db = get_database()
    cursor = db["predictions"].find().sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    return await populate_history_metadata(history, db)

@router.post("/")
async def predict_ecg(
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(None),
    patient_name: Optional[str] = Form(None),
    patient_age: Optional[str] = Form(None),
    patient_gender: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    image_bytes = await file.read()
    
    # Determine which user ID to associate with
    # If doctor provides patient_id, use it, otherwise use doctor's ID
    user_id = patient_id if patient_id else current_user["_id"]
    
    # If current user is a doctor/admin, they are the 'doctor_id'
    doctor_id = current_user["_id"] if current_user.get("role") in ["doctor", "admin"] else None
    
    # Construct notes from metadata if provided
    notes = ""
    if patient_name:
        notes = f"Patient: {patient_name} | Age: {patient_age} | Gender: {patient_gender}"
    
    # Run prediction
    result = await run_prediction(image_bytes, user_id, file.filename, notes=notes, doctor_id=doctor_id)
    
    return result

@router.delete("/{prediction_id}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def delete_prediction(prediction_id: str):
    db = get_database()
    result = await db["predictions"].delete_one({"_id": ObjectId(prediction_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return {"message": "Prediction deleted successfully"}

@router.put("/{prediction_id}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def update_prediction_metadata(
    prediction_id: str,
    patient_name: Optional[str] = Form(None),
    patient_age: Optional[str] = Form(None),
    patient_gender: Optional[str] = Form(None)
):
    db = get_database()
    
    # Construct new notes string
    notes = ""
    if patient_name:
        notes = f"Patient: {patient_name} | Age: {patient_age} | Gender: {patient_gender}"
    
    update_data = {"notes": notes}
    
    result = await db["predictions"].update_one(
        {"_id": ObjectId(prediction_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prediction not found")
        
    return {"message": "Prediction updated successfully"}

@router.get("/history/{user_id}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_patient_history(user_id: str):
    db = get_database()
    cursor = db["predictions"].find({"user_id": user_id}).sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    return await populate_history_metadata(history, db)

@router.get("/history/name/{patient_name}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_patient_history_by_name(patient_name: str):
    db = get_database()
    # Search for patients where the name is in the notes
    cursor = db["predictions"].find({"notes": {"$regex": f"Patient: {patient_name}"}}).sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    return await populate_history_metadata(history, db)

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    db = get_database()
    cursor = db["predictions"].find({"user_id": current_user["_id"]}).sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    return await populate_history_metadata(history, db)

@router.get("/history/unified/{identifier}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_unified_patient_history(identifier: str):
    db = get_database()
    import re
    
    history = []
    
    # 1. Try treating identifier as a User ID (Registered Patient)
    try:
        user_obj_id = ObjectId(identifier)
        user = await db["users"].find_one({"_id": user_obj_id})
        
        if user:
            # Find by user_id OR by name in notes
            cursor = db["predictions"].find({
                "$or": [
                    {"user_id": identifier},
                    {"notes": {"$regex": f"Patient: {user['name']}"}}
                ]
            }).sort("timestamp", -1)
            history = await cursor.to_list(length=100)
            return await populate_history_metadata(history, db)
    except:
        pass

    # 2. Try treating identifier as a Prediction ID (Clinical Record)
    try:
        pred_obj_id = ObjectId(identifier)
        prediction = await db["predictions"].find_one({"_id": pred_obj_id})
        
        if prediction:
            # Extract name from notes if possible
            notes = prediction.get("notes", "")
            name_match = re.search(r"Patient:\s*([^|]+)", notes)
            if name_match:
                name = name_match.group(1).strip()
                # Find all by name
                cursor = db["predictions"].find({"notes": {"$regex": f"Patient: {name}"}}).sort("timestamp", -1)
                history = await cursor.to_list(length=100)
            else:
                # If no name, just return this one prediction
                history = [prediction]
                
            return await populate_history_metadata(history, db)
    except:
        pass

    # 3. Last resort: Treat identifier as a Name directly
    cursor = db["predictions"].find({"notes": {"$regex": f"Patient: {identifier}"}}).sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    return await populate_history_metadata(history, db)
