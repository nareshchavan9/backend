# Arrhythmia Detection Backend

A production-ready FastAPI backend for AI-powered ECG classification.

## Features

- **JWT Authentication**: Secure user registration and login with role-based access (Patient, Doctor, Admin).
- **ECG Classification**: Image upload and processing for arrhythmia prediction using TensorFlow.
- **Automated Reporting**: Generation of downloadable PDF reports for patients and doctors.
- **Scalable Architecture**: Modular design ready for AI health assistant and chatbot integration.
- **Database Persistence**: Asynchronous MongoDB integration using Motor.
- **Deployment Ready**: Includes Dockerfile and environment configuration.

## Tech Stack

- **Framework**: FastAPI
- **Database**: MongoDB (Motor)
- **ML/DL**: TensorFlow, NumPy, Pillow
- **Auth**: JWT, bcrypt (Passlib)
- **Reporting**: ReportLab
- **Containerization**: Docker

## Getting Started

### Prerequisites

- Python 3.10+
- MongoDB instance (Local or Atlas)

### Installation

1. Clone the repository
2. Navigate to the backend directory:
   ```bash
   cd backend
   ```
3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Update the variables with your configuration.

### Running the Server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.
Access the interactive documentation at `http://localhost:8000/docs`.

### Using Docker

```bash
docker build -t arrhythmia-backend .
docker run -p 8000:8000 arrhythmia-backend
```

## Project Structure

- `app/routes`: API endpoints for Auth, Prediction, Reports, and AI Agent.
- `app/models`: Pydantic models for data validation.
- `app/services`: Business logic (Model loading, preprocessing, PDF generation).
- `app/database`: Database connection logic.
- `app/middleware`: Authentication and authorization logic.
- `pretrained_model`: Placeholder for the AI model file.
- `uploads`: Storage for uploaded ECG images.
