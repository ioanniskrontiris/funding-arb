import os, json, requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class LLMProvider:
    def available(self) -> bool: ...
    def chat_json(self, messages: List[Dict[str, str]], model: Optional[str] = None,
                  temperature: float = 0.2) -> Optional[Dict[str, Any]]: ...

class NullProvider(LLMProvider):
    def available(self) -> bool: return False
    def chat_json(self, messages, model=None, temperature=0.2): return None

class OllamaChat(LLMProvider):
    def __init__(self):
        self.base = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
        self.model = os.getenv("LLM_MODEL", "llama3:8b")
        self.endpoint = f"{self.base}/api/chat"
        try:
            requests.get(self.base, timeout=1)
            self._ok = True
        except Exception:
            self._ok = False
    def available(self) -> bool: return self._ok
    def chat_json(self, messages, model=None, temperature=0.2):
        if not self.available(): return None
        payload = {
            "model": model or self.model,
            "messages": messages,
            "options": {"temperature": 0.0},
            "stream": False,
            "format": "json",  # enforce JSON output
        }
        r = requests.post(self.endpoint, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        txt = data.get("message", {}).get("content", "")
        try:
            return json.loads(txt)
        except Exception:
            return {"_raw": txt}

def get_provider() -> LLMProvider:
    p = OllamaChat()
    return p if p.available() else NullProvider()