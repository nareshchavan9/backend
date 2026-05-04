import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
os.environ["KERAS_BACKEND"] = "tensorflow"
load_dotenv()

from app.routes import auth, predict, reports, ai_agent
from app.database.db import connect_to_mongo, close_mongo_connection

app = FastAPI(
    title="Arrhythmia Detection API",
    description="Backend API for AI-powered ECG classification and arrhythmia detection.",
    version="1.0.0"
)

# CORS configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

# Add custom origins from env if provided (comma-separated)
env_origins = os.getenv("CORS_ORIGINS")
if env_origins:
    origins.extend([o.strip() for o in env_origins.split(",")])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if os.getenv("ENVIRONMENT") == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup and Shutdown events
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()
    # Create upload directory if not exists
    os.makedirs(os.getenv("UPLOAD_DIR", "uploads"), exist_ok=True)

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(predict.router, prefix="/api/predict", tags=["Prediction"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(ai_agent.router, prefix="/api/ai", tags=["AI Agent"])

@app.get("/")
async def root():
    from app.services.model_loader import model_loader
    return {
        "message": "Welcome to Arrhythmia Detection API",
        "status": "running",
        "ai_model": {
            "loaded": model_loader.model is not None,
            "path": os.getenv("MODEL_PATH"),
            "labels": model_loader.get_labels()
        }
    }
