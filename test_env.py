from dotenv import load_dotenv
import os

load_dotenv()

print("App key is:", os.getenv("BETFAIR_API_KEY"))
