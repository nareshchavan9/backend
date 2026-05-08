from fastapi import APIRouter, Depends, HTTPException, Response, Query
from typing import Optional
from app.middleware.auth_middleware import get_current_user, check_role
from app.database.db import get_database
from app.services.report_service import generate_pdf_report
from bson import ObjectId
import re
import time

router = APIRouter()

@router.get("/{prediction_id}")
async def get_report(
    prediction_id: str,
    current_user: dict = Depends(get_current_user)
):
    start_time = time.time()
    db = get_database()
    
    # 1. Fetch prediction record
    prediction = await db["predictions"].find_one({"_id": ObjectId(prediction_id)})
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    # Security check
    if str(prediction["user_id"]) != str(current_user["_id"]) and current_user["role"] not in ["doctor", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this report")
    
    # 2. INSTANT METADATA RESOLUTION
    # Use denormalized data to avoid additional DB lookups
    patient_data = {
        "name": prediction.get("patient_name", "Unknown Patient"),
        "email": "N/A (Clinical Records)",
        "age": "N/A",
        "gender": "N/A"
    }
    
    # Quick regex for age/gender
    notes = prediction.get("notes", "")
    if notes:
        try:
            age_match = re.search(r"Age:\s*(\d+)", notes)
            gender_match = re.search(r"Gender:\s*(\w+)", notes)
            if age_match: patient_data["age"] = age_match.group(1)
            if gender_match: patient_data["gender"] = gender_match.group(1)
        except: pass

    doctor_data = {"name": prediction.get("doctor_name", "Clinical Automated System")}
    
    # 3. Generate PDF
    pdf_buffer = generate_pdf_report(prediction, patient_data, doctor_data)
    
    generation_time = (time.time() - start_time) * 1000 # in ms
    print(f"REPORT GENERATED IN {generation_time:.2f}ms")
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=report_{prediction_id}.pdf",
            "X-Process-Time": f"{generation_time:.2f}ms",
            "Cache-Control": "no-cache" # Force fresh for testing
        }
    )

@router.get("/admin/patients", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_all_patients(search: Optional[str] = Query(None)):
    db = get_database()
    query = {"role": "patient"}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}}
        ]
    cursor = db["users"].find(query, {"password_hash": 0})
    patients = await cursor.to_list(length=100)
    for p in patients: p["_id"] = str(p["_id"])
    return patients
