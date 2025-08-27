# get_chat_id.py
import os, requests, sys
from dotenv import load_dotenv

# load from .env into environment
load_dotenv()

token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    print("Set TELEGRAM_BOT_TOKEN in your environment or .env first.")
    sys.exit(1)

resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
print(resp)

if isinstance(resp, dict) and resp.get("result"):
    msg = resp["result"][-1].get("message") or resp["result"][-1].get("channel_post") or {}
    chat = msg.get("chat", {})
    print("\nchat id:", chat.get("id"))
else:
    print("\nNo messages yet — send 'hi' to your bot in Telegram and run again.")