def parse_text(raw: bytes) -> str:
    """Already validated as UTF-8 by detection.py — just decode."""
    return raw.decode("utf-8")
