import os
import sys
from dotenv import load_dotenv

# .env ফাইল থেকে ভ্যালু লোড করবে (যদি থাকে)
load_dotenv()

# Fetching variables from Environment
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = os.environ.get("OWNER_ID")

# Validation check
if not all([API_ID, API_HASH, BOT_TOKEN, OWNER_ID]):
    print("❌ ERROR: Missing one or more environment variables (API_ID, API_HASH, BOT_TOKEN, OWNER_ID).")
    sys.exit(1)

try:
    API_ID = int(API_ID)
    OWNER_ID = int(OWNER_ID)
except ValueError:
    print("❌ ERROR: API_ID and OWNER_ID must be numeric values.")
    sys.exit(1)
DEBUG_MODE = os.environ.get("DEBUG_MODE", "False").lower() == "true"
