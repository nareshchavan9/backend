import numpy as np
from PIL import Image
import io

from app.services.model_loader import model_loader

def preprocess_image(image_bytes: bytes, target_size=(128, 128)):
    """
    Preprocess the uploaded ECG image for model inference.
    """
    # Load image from bytes
    image = Image.open(io.BytesIO(image_bytes))
    
    # Convert to RGB if it's not
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # Resize to model input size
    image = image.resize(target_size)
    
    # Convert to numpy array and normalize
    img_array = np.array(image) / 255.0
    
    # Add batch dimension
    img_array = np.expand_dims(img_array, axis=0)
    
    return img_array

def get_class_label(prediction_probs):
    """
    Map model output probabilities to class labels.
    Returns the top label, confidence, and a full breakdown of all classes.
    """
    classes = model_loader.get_labels()
    probs = prediction_probs[0]
    max_index = int(np.argmax(probs))
    confidence = float(probs[max_index])
    
    # Top label
    if max_index < len(classes):
        label_code = classes[max_index]
        label = model_loader.get_display_name(label_code)
    else:
        label = "Other"
    
    # Full breakdown: all classes with their percentages
    breakdown = []
    for i, prob in enumerate(probs):
        if i < len(classes):
            code = classes[i]
            display = model_loader.get_display_name(code)
        else:
            display = f"Class {i}"
        breakdown.append({
            "label": display,
            "percentage": round(float(prob) * 100, 2)
        })
    
    # Sort by percentage descending
    breakdown.sort(key=lambda x: x["percentage"], reverse=True)
        
    return label, confidence, breakdown
