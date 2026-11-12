"""One Gemini client per API key, shared by every module that calls Gemini."""
import os
import threading

try:
    from google import genai
except ImportError:
    genai = None

_lock = threading.Lock()
_key = None
_client = None


def gemini_client():
    """The shared client for the current key, or None (no SDK, no key, or the client would not build)."""
    global _key, _client
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if genai is None or not key:
        return None
    with _lock:
        # Rebuild only when the key changes, so every caller shares one connection pool.
        if _client is None or key != _key:
            try:
                _client = genai.Client(api_key=key)
            except Exception:  # noqa: BLE001 - a bad key must not crash the caller
                return None
            _key = key
        return _client
