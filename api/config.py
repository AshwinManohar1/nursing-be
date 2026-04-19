import os
from dotenv import load_dotenv
load_dotenv()

OPEN_API_KEY = os.getenv("OPEN_API_KEY") or os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
MONGO_URI=os.getenv("MONGO_URI") or os.getenv("MONGO_URI")
PORT=os.getenv("PORT") or os.getenv("PORT")

# JWT Configuration (RS256 only - run scripts/generate_jwt_keys.py to generate)
JWT_PRIVATE_KEY = os.getenv("JWT_PRIVATE_KEY")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY")

# Shorter expiry for security
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES") or "15")
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS") or "7")

SUPER_ADMIN_SECRET_KEY = os.getenv("SUPER_ADMIN_SECRET_KEY") or "your-user-creation-secret-key-change-this"