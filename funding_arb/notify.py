# funding_arb/notify.py
import os
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def _enabled() -> bool:
    return bool(TOKEN and CHAT_ID)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.6, max=4))
def send_telegram(text: str, disable_web_page_preview: bool = True):
    """
    Send a Telegram message to your configured chat.
    Uses NO parse_mode to avoid Markdown escaping issues.
    """
    if not _enabled():
        print("Telegram not configured. Skipping send.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
        # no parse_mode
    }
    r = requests.post(url, json=payload, timeout=10)
    if r.status_code >= 300:
        raise RuntimeError(f"Telegram error {r.status_code}: {r.text}")
    return True

# Plain-text formatters (no asterisks/underscores)
def fmt_status(opened: bool, accrued_bps: float, est_pnl: float) -> str:
    return f"status — open={opened}, accrued={accrued_bps:.4f} bps, est_pnl={est_pnl:.6f} USDT"

def fmt_open(bpsd: float, action: int, cost_bps: float) -> str:
    return f"OPEN bpsd={bpsd:.2f}, action={action}, exec_cost={cost_bps:.3f} bps"

def fmt_close(bpsd: float, action: int, cost_bps: float) -> str:
    return f"CLOSE bpsd={bpsd:.2f}, action={action}, exec_cost={cost_bps:.3f} bps"

def fmt_risk(reason: str, est_pnl: float) -> str:
    return f"RISK HALT reason={reason}, est_pnl={est_pnl:.4f} USDT"