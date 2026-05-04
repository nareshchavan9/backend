from fastapi import APIRouter, Depends, HTTPException, Response
from app.middleware.auth_middleware import get_current_user, check_role
from app.database.db import get_database
from app.services.report_service import generate_pdf_report
from bson import ObjectId

router = APIRouter()

@router.get("/{prediction_id}")
async def get_report(
    prediction_id: str,
    current_user: dict = Depends(get_current_user)
):
    db = get_database()
    prediction = await db["predictions"].find_one({"_id": ObjectId(prediction_id)})
    
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    # Security: Ensure user can only access their own reports unless they are doctor/admin
    if str(prediction["user_id"]) != str(current_user["_id"]) and current_user["role"] not in ["doctor", "admin"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this report")
    
    # Identify Patient and Doctor
    raw_user = await db["users"].find_one({"_id": ObjectId(prediction["user_id"])})
    
    patient_data = raw_user
    doctor = None
    
    # If the record is stored under a doctor's ID (clinical patient)
    if raw_user and raw_user.get("role") in ["doctor", "admin"]:
        doctor = raw_user
        # Extract patient info from notes
        import re
        notes = prediction.get("notes", "")
        p_name = re.search(r"Patient:\s*([^|]+)", notes)
        p_age = re.search(r"Age:\s*(\d+)", notes)
        p_gender = re.search(r"Gender:\s*(\w+)", notes)
        
        patient_data = {
            "name": p_name.group(1).strip() if p_name else "Clinical Patient",
            "email": "N/A (Clinical)",
            "age": p_age.group(1) if p_age else "N/A",
            "gender": p_gender.group(1) if p_gender else "N/A"
        }
    
    # Also check explicit doctor_id field (for newer records)
    doctor_id = prediction.get("doctor_id")
    if doctor_id:
        try:
            explicit_doctor = await db["users"].find_one({"_id": ObjectId(doctor_id)})
            if explicit_doctor:
                doctor = explicit_doctor
        except:
            pass
            
    pdf_buffer = generate_pdf_report(prediction, patient_data, doctor)
    
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{prediction_id}.pdf"}
    )

@router.get("/admin/patients", dependencies=[Depends(check_role(["doctor", "admin"]))])
async def get_all_patients():
    db = get_database()
    cursor = db["users"].find({"role": "patient"}, {"password_hash": 0})
    patients = await cursor.to_list(length=100)
    
    for p in patients:
        p["_id"] = str(p["_id"])
    return patients
