import os
import keras
from dotenv import load_dotenv

load_dotenv()

class ModelLoader:
    _instance = None
    model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelLoader, cls).__new__(cls)
            cls._instance._load_model()
        return cls._instance

    def _load_model(self):
        model_path = os.getenv("MODEL_PATH", "pretrained_model/best_final.keras")
        label_path = os.getenv("LABEL_PATH", "pretrained_model/label_map.json")
        
        # Load Model
        print(f"DEBUG: Attempting to load model from {model_path}...")
        if os.path.exists(model_path):
            try:
                # Use compile=False because we only need the model for inference
                # and don't have the definitions for custom losses/optimizers
                self.model = keras.models.load_model(model_path, compile=False)
                print(f"SUCCESS: Model loaded successfully from {model_path}")
                print(f"DEBUG: Model input shape: {self.model.input_shape}")
            except Exception as e:
                print(f"ERROR: Failed to load model: {e}")
                self.model = None
        else:
            print(f"WARNING: Model file not found at {model_path}.")
            self.model = None

        # Load Labels
        if os.path.exists(label_path):
            try:
                import json
                with open(label_path, 'r') as f:
                    data = json.load(f)
                    # Support both list of classes or the inv_label_map
                    if "classes" in data:
                        self.labels = data["classes"]
                    elif "inv_label_map" in data:
                        # Sort keys numerically to ensure correct order
                        inv_map = data["inv_label_map"]
                        self.labels = [inv_map[str(i)] for i in range(len(inv_map))]
                    else:
                        self.labels = ["Unknown"]
                    
                    # Load display names for mapping (e.g. N -> Normal Beat)
                    self.display_names = data.get("display_names", {})

                print(f"Labels loaded successfully from {label_path}: {self.labels}")
            except Exception as e:
                print(f"Error loading labels: {e}")
                self.labels = ["Normal", "PVC", "APC", "LBBB", "RBBB", "Atrial Fibrillation"] # Fallback
                self.display_names = {}
        else:
            print(f"Label file not found at {label_path}. Using default labels.")
            self.labels = ["Normal", "PVC", "APC", "LBBB", "RBBB", "Atrial Fibrillation"]
            self.display_names = {}

    def predict(self, processed_image):
        if self.model:
            return self.model.predict(processed_image)
        else:
            # Fallback mock prediction for demonstration if model is missing
            import numpy as np
            print("WARNING: Using mock prediction because model is not loaded.")
            num_classes = len(self.labels) if hasattr(self, 'labels') else 6
            return np.random.dirichlet(np.ones(num_classes), size=1)

    def get_labels(self):
        return getattr(self, 'labels', [])

    def get_display_name(self, label_code):
        """Map a class code (like 'N') to its full name (like 'Normal Beat')."""
        return self.display_names.get(label_code, label_code)

# Singleton instance
model_loader = ModelLoader()
