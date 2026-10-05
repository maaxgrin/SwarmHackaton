"""Explicit in-memory credentials and a bounded transport for DeepSeek pilots."""
import os
from urllib.request import build_opener


def require_deepseek_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Set DEEPSEEK_API_KEY in the environment before running a DeepSeek pilot")
    return key


class DeepSeekTimeout:
    def __init__(self, *handlers):
        self.opener = build_opener(*handlers)

    def open(self, request, timeout=None):
        if not request.full_url.startswith("https://api.deepseek.com/"):
            raise RuntimeError("Unexpected DeepSeek pilot provider endpoint")
        return self.opener.open(request, timeout=180)
