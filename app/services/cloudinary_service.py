import os
import cloudinary
import cloudinary.uploader
from cloudinary.utils import cloudinary_url
from dotenv import load_dotenv

load_dotenv()

# Configuration 
cloudinary.config( 
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"), 
    api_key = os.getenv("CLOUDINARY_API_KEY"), 
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
    secure = True
)

def upload_image_to_cloud(image_bytes: bytes, folder: str = "ecg_uploads"):
    """
    Uploads image bytes to Cloudinary and returns the secure URL.
    """
    try:
        response = cloudinary.uploader.upload(
            image_bytes,
            folder=folder,
            resource_type="image"
        )
        return response.get("secure_url")
    except Exception as e:
        print(f"Cloudinary Upload Error: {e}")
        return None
