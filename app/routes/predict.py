from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, Query, BackgroundTasks
from typing import Optional, List
from app.middleware.auth_middleware import get_current_user, check_role
from app.services.predict_service import run_prediction
from app.database.db import get_database
from bson import ObjectId

router = APIRouter()

# -------------------------------------------------------------------------
# OPTIMIZATION: BATCH PROCESSING & DENORMALIZATION SUPPORT
# -------------------------------------------------------------------------
async def populate_history_metadata(history, db):
    if not history:
        return []

    user_ids_to_fetch = set()
    for item in history:
        item["_id"] = str(item["_id"])
        if not item.get("patient_name") or not item.get("doctor_name"):
            uid = item.get("user_id")
            did = item.get("doctor_id")
            if uid and ObjectId.is_valid(str(uid)):
                user_ids_to_fetch.add(ObjectId(str(uid)))
            if did and ObjectId.is_valid(str(did)):
                user_ids_to_fetch.add(ObjectId(str(did)))

    users_map = {}
    if user_ids_to_fetch:
        users_cursor = db["users"].find({"_id": {"$in": list(user_ids_to_fetch)}}, {"name": 1, "role": 1})
        async for user in users_cursor:
            users_map[str(user["_id"])] = user

    for item in history:
        if not item.get("patient_name"):
            notes = item.get("notes", "")
            if notes and "Patient:" in notes:
                try: item["patient_name"] = notes.split("Patient:")[1].split("|")[0].strip()
                except: pass
            if not item.get("patient_name"):
                uid_str = str(item.get("user_id"))
                user_data = users_map.get(uid_str)
                item["patient_name"] = user_data.get("name", "Unknown") if user_data else "Unknown"
            
        if not item.get("doctor_name"):
            did_str = str(item.get("doctor_id"))
            doctor_data = users_map.get(did_str)
            if doctor_data:
                item["doctor_name"] = f"Dr. {doctor_data.get('name')}"
            else:
                uid_str = str(item.get("user_id"))
                u_data = users_map.get(uid_str)
                if u_data and u_data.get("role") in ["doctor", "admin"]:
                    item["doctor_name"] = f"Dr. {u_data.get('name')}"
                else:
                    item["doctor_name"] = "Self-Tested" if u_data else "System"

    return history

# -------------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------------
@router.get("/all", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_all_predictions(page: int = Query(1, ge=1), limit: int = Query(20, le=100)):
    db = get_database()
    skip = (page - 1) * limit
    cursor = db["predictions"].find({}, {"breakdown": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    history = await cursor.to_list(length=limit)
    return await populate_history_metadata(history, db)

@router.post("/")
async def predict_ecg(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    patient_id: Optional[str] = Form(None),
    patient_name: Optional[str] = Form(None),
    patient_age: Optional[str] = Form(None),
    patient_gender: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    image_bytes = await file.read()
    user_id = patient_id if patient_id else current_user["_id"]
    doctor_id = current_user["_id"] if current_user.get("role") in ["doctor", "admin"] else None
    
    notes = ""
    if patient_name:
        notes = f"Patient: {patient_name} | Age: {patient_age} | Gender: {patient_gender}"
    
    # PASSING background_tasks here for optimized speed
    result = await run_prediction(image_bytes, user_id, file.filename, notes=notes, doctor_id=doctor_id, background_tasks=background_tasks)
    return result

@router.get("/history")
async def get_history(page: int = Query(1, ge=1), limit: int = Query(20, le=100), current_user: dict = Depends(get_current_user)):
    db = get_database()
    skip = (page - 1) * limit
    cursor = db["predictions"].find({"user_id": current_user["_id"]}, {"breakdown": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    history = await cursor.to_list(length=limit)
    return await populate_history_metadata(history, db)

@router.get("/history/unified/{identifier}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_unified_patient_history(identifier: str, page: int = Query(1, ge=1), limit: int = Query(20, le=100)):
    db = get_database()
    skip = (page - 1) * limit
    import re
    try:
        user_obj_id = ObjectId(identifier)
        user = await db["users"].find_one({"_id": user_obj_id})
        if user:
            cursor = db["predictions"].find({
                "$or": [
                    {"user_id": identifier},
                    {"notes": {"$regex": f"Patient: {user['name']}"}},
                    {"patient_name": user['name']}
                ]
            }, {"breakdown": 0}).sort("timestamp", -1).skip(skip).limit(limit)
            history = await cursor.to_list(length=limit)
            return await populate_history_metadata(history, db)
    except: pass

    cursor = db["predictions"].find({
        "$or": [
            {"notes": {"$regex": f"Patient: {identifier}"}},
            {"patient_name": {"$regex": identifier, "$options": "i"}}
        ]
    }, {"breakdown": 0}).sort("timestamp", -1).skip(skip).limit(limit)
    history = await cursor.to_list(length=limit)
    return await populate_history_metadata(history, db)

@router.delete("/{prediction_id}", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def delete_prediction(prediction_id: str):
    db = get_database()
    result = await db["predictions"].delete_one({"_id": ObjectId(prediction_id)})
    if result.deleted_count == 0: raise HTTPException(status_code=404, detail="Prediction not found")
    return {"message": "Prediction deleted successfully"}

@router.get("/{prediction_id}")
async def get_prediction_detail(prediction_id: str):
    db = get_database()
    prediction = await db["predictions"].find_one({"_id": ObjectId(prediction_id)})
    if not prediction: raise HTTPException(status_code=404, detail="Prediction not found")
    history = await populate_history_metadata([prediction], db)
    return history[0]
