from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from app.middleware.auth_middleware import get_current_user
from app.database.db import get_database
from datetime import datetime
import os
import google.generativeai as genai
from PIL import Image
import io
from bson import ObjectId

router = APIRouter()

@router.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    """
    Retrieve all conversation sessions for the current user.
    """
    db = get_database()
    user_id = str(current_user["_id"])
    
    conversations = await db.conversations.find({"user_id": user_id}).sort("updated_at", -1).to_list(100)
    
    for conv in conversations:
        conv["_id"] = str(conv["_id"])
    
    return conversations

@router.get("/conversations/{conversation_id}")
async def get_conversation_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """
    Retrieve all messages for a specific conversation.
    """
    db = get_database()
    user_id = str(current_user["_id"])
    
    # Verify ownership
    conv = await db.conversations.find_one({"_id": ObjectId(conversation_id), "user_id": user_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    messages = await db.chat_messages.find({"conversation_id": conversation_id}).sort("timestamp", 1).to_list(500)
    
    for msg in messages:
        msg["_id"] = str(msg["_id"])
        
    return messages

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    """
    Delete a specific conversation and all its messages.
    """
    db = get_database()
    user_id = str(current_user["_id"])
    
    await db.conversations.delete_one({"_id": ObjectId(conversation_id), "user_id": user_id})
    await db.chat_messages.delete_many({"conversation_id": conversation_id})
    
    return {"message": "Conversation deleted", "status": "success"}

@router.post("/chat")
async def chat_with_agent(
    message: str = Form(...),
    conversation_id: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user)
):
    """
    AI Health Assistant Endpoint with Session Support
    """
    db = get_database()
    user_id = str(current_user["_id"])
    
    # --- Rate Limiting (Optional but good) ---
    # ... (can be kept from previous version if desired) ...

    # 1. Handle Conversation Session
    is_new_chat = False
    if not conversation_id or conversation_id == "null":
        is_new_chat = True
        # Generate title from first message
        title = message[:40] + ("..." if len(message) > 40 else "")
        conv_doc = {
            "user_id": user_id,
            "title": title,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        result = await db.conversations.insert_one(conv_doc)
        conversation_id = str(result.inserted_id)
    else:
        # Update timestamp for sorting
        await db.conversations.update_one(
            {"_id": ObjectId(conversation_id)},
            {"$set": {"updated_at": datetime.utcnow()}}
        )

    # 2. Save user message
    user_msg_doc = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "text": message,
        "sender": "user",
        "timestamp": datetime.utcnow()
    }
    await db.chat_messages.insert_one(user_msg_doc)

    # 3. Get Context (Latest Prediction)
    latest_pred = await db.predictions.find_one(
        {"user_id": user_id},
        sort=[("timestamp", -1)]
    )
    pred_context = "No previous reports found."
    if latest_pred:
        pred_context = f"Latest Diagnosis: {latest_pred['prediction']}, Confidence: {(latest_pred['confidence'] * 100):.1f}%, Date: {latest_pred['timestamp'].strftime('%Y-%m-%d')}"

    # 4. Generate AI Reply
    api_key = os.getenv("GOOGLE_API_KEY")
    reply = ""
    mode = "fallback"
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-flash-latest')
            role = current_user.get('role', 'patient')
            
            system_prompt = (
                f"You are a professional medical AI assistant. User role: {role}. \n"
                f"LATEST REPORT: {pred_context}\n"
                f"Provide concise, medically safe advice. Disclaimer: You are an AI, not a doctor."
            )
            
            prompt = f"User asked: '{message}'"
            inputs = [system_prompt, prompt]
            
            if file:
                file_bytes = await file.read()
                if file.content_type.startswith("image/"):
                    img = Image.open(io.BytesIO(file_bytes))
                    inputs.append(img)
                else:
                    inputs.append({"mime_type": file.content_type, "data": file_bytes})
                    
            response = await model.generate_content_async(inputs)
            reply = response.text
            mode = "gemini"
        except Exception as e:
            print(f"Gemini API Error: {e}")

    if not reply:
        # --- Basic Fallback logic ... (kept simple for brevity) ---
        reply = f"I am currently operating in basic mode. Regarding your query about '{message[:20]}...', please ensure you consult a cardiologist for clinical advice."

    # 5. Save bot reply
    bot_msg_doc = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "text": reply,
        "sender": "bot",
        "timestamp": datetime.utcnow()
    }
    await db.chat_messages.insert_one(bot_msg_doc)

    return {
        "reply": reply,
        "conversation_id": conversation_id,
        "is_new_chat": is_new_chat,
        "status": "success",
        "mode": mode
    }

@router.get("/recommendations")
async def get_recommendations(current_user: dict = Depends(get_current_user)):
    return {"recommendations": ["Maintain a healthy diet", "Monitor your heart rate regularly"], "status": "planned"}
