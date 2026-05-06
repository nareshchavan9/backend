import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=api_key)

system_instruction = "You are a medical AI assistant. Answer clearly."
model_name = 'gemini-flash-latest'

print(f"Testing model: {model_name} with system_instruction...")
try:
    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction
    )
    response = model.generate_content("Hello, can you help me with my heart health?")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
