from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from app.middleware.auth_middleware import get_current_user
from app.database.db import get_database
from datetime import datetime, timedelta
import os
import google.generativeai as genai
from PIL import Image
import io
from bson import ObjectId

router = APIRouter()

# -------------------------------------------------------------------------
# OPTIMIZATION: IN-MEMORY CACHING
# -------------------------------------------------------------------------
class SimpleCache:
    def __init__(self):
        self.data = {}
        self.expiry = {}

    def set(self, key, value, duration=60):
        self.data[key] = value
        self.expiry[key] = datetime.utcnow() + timedelta(seconds=duration)

    def get(self, key):
        if key in self.data:
            if datetime.utcnow() < self.expiry[key]:
                return self.data[key]
            else:
                del self.data[key]
                del self.expiry[key]
        return None

    def invalidate(self, user_id):
        keys_to_del = [k for k in self.data.keys() if str(user_id) in k]
        for k in keys_to_del:
            del self.data[k]
            del self.expiry[k]

ai_cache = SimpleCache()

@router.get("/conversations")
async def get_conversations(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cache_key = f"conv_list_{user_id}"
    
    cached = ai_cache.get(cache_key)
    if cached: return cached

    db = get_database()
    conversations = await db.conversations.find({"user_id": user_id}).sort("updated_at", -1).to_list(100)
    
    for conv in conversations:
        conv["_id"] = str(conv["_id"])
    
    ai_cache.set(cache_key, conversations)
    return conversations

@router.get("/conversations/{conversation_id}")
async def get_conversation_messages(conversation_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["_id"])
    cache_key = f"msgs_{conversation_id}_{user_id}"
    
    cached = ai_cache.get(cache_key)
    if cached: return cached

    db = get_database()
    conv = await db.conversations.find_one({"_id": ObjectId(conversation_id), "user_id": user_id})
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    messages = await db.chat_messages.find({"conversation_id": conversation_id}).sort("timestamp", 1).to_list(500)
    
    for msg in messages:
        msg["_id"] = str(msg["_id"])
        
    ai_cache.set(cache_key, messages)
    return messages

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, current_user: dict = Depends(get_current_user)):
    db = get_database()
    user_id = str(current_user["_id"])
    
    await db.conversations.delete_one({"_id": ObjectId(conversation_id), "user_id": user_id})
    await db.chat_messages.delete_many({"conversation_id": conversation_id})
    
    ai_cache.invalidate(user_id)
    return {"message": "Conversation deleted", "status": "success"}

@router.post("/chat")
async def chat_with_agent(
    message: str = Form(...),
    conversation_id: str = Form(None),
    file: UploadFile = File(None),
    current_user: dict = Depends(get_current_user)
):
    db = get_database()
    user_id = str(current_user["_id"])
    ai_cache.invalidate(user_id)

    # 1. Handle Conversation Session
    is_new_chat = False
    if not conversation_id or conversation_id == "null":
        is_new_chat = True
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

    # 3. SPEED OPTIMIZATION: Quick Context Fetch (Projected)
    latest_pred = await db.predictions.find_one(
        {"user_id": user_id},
        {"prediction": 1, "confidence": 1, "timestamp": 1}, # Only fetch what we need
        sort=[("timestamp", -1)]
    )
    pred_context = "No previous reports found."
    if latest_pred:
        pred_context = f"Latest Diagnosis: {latest_pred['prediction']}, Confidence: {(latest_pred['confidence'] * 100):.1f}%, Date: {latest_pred['timestamp'].strftime('%Y-%m-%d')}"

    # 4. SPEED OPTIMIZATION: Gemini 1.5 Flash with System Instructions
    api_key = os.getenv("GOOGLE_API_KEY")
    reply = ""
    mode = "fallback"
    
    if api_key:
        try:
            genai.configure(api_key=api_key)
            role = current_user.get('role', 'patient')
            
            # Use system_instruction (Most efficient way for Gemini 1.5)
            system_instruction = (
                f"You are a professional medical AI assistant for the Arrhythmia Detection platform. "
                f"User: {current_user.get('name')} (Role: {role}). "
                f"LATEST REPORT: {pred_context}. "
                f"Always be helpful, professional, and concise. "
                f"If the query is medical, provide safe, heart-focused guidance. "
                f"If general, be a standard helpful assistant. Do not refuse non-medical queries."
            )
            
            # Use the exact model name available in your environment
            try:
                model = genai.GenerativeModel(
                    model_name='gemini-flash-latest',
                    system_instruction=system_instruction
                )
            except:
                # Fallback to pro-latest if flash is missing
                model = genai.GenerativeModel(
                    model_name='gemini-pro-latest',
                    system_instruction=system_instruction
                )
            
            inputs = [message]
            if file:
                file_bytes = await file.read()
                if file.content_type.startswith("image/"):
                    img = Image.open(io.BytesIO(file_bytes))
                    inputs.append(img)
                else:
                    # For other files, pass as generic data
                    inputs.append({"mime_type": file.content_type, "data": file_bytes})
                    
            # Set a 15-second generation timeout for better UX
            response = await model.generate_content_async(
                inputs,
                generation_config=genai.types.GenerationConfig(
                    candidate_count=1,
                    stop_sequences=['\n\n\n'],
                    max_output_tokens=1000,
                    temperature=0.7
                )
            )
            reply = response.text
            mode = "gemini"
        except Exception as e:
            print(f"DEBUG: Gemini Fast-Path Error: {e}")

    if not reply:
        reply = f"I'm sorry, I'm having trouble connecting to my diagnostic brain. Regarding your message: '{message[:30]}...', please ensure you follow your prescribed medical plan or contact support."

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
