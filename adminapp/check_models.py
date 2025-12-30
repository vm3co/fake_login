import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key:
    # Try to read from .env manually if load_dotenv fails or system env not set
    try:
        with open('.env') as f:
            for line in f:
                if line.startswith('GOOGLE_API_KEY='):
                    api_key = line.strip().split('=')[1]
                    break
    except:
        pass

if not api_key:
    print("Error: GOOGLE_API_KEY not found in environment or .env")
else:
    print(f"Using API Key: {api_key[:5]}...{api_key[-3:]}")
    try:
        genai.configure(api_key=api_key)
        print("Listing available models:")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"Error listing models: {e}")
