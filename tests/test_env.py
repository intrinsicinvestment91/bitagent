import os
from dotenv import load_dotenv

load_dotenv()

print("LNBITS_API_KEY:", os.getenv("LNBITS_API_KEY"))
print("LNBITS_API_BASE:", os.getenv("LNBITS_API_BASE"))
