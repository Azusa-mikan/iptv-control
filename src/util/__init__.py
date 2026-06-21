from urllib.parse import urlparse, quote

def is_url(url: str) -> bool:
    return url.startswith(('http://', 'https://'))

def safe_url(url: str) -> str:
    parsed = urlparse(url)
    path = quote(parsed.path, safe='/%')
    base = f"{parsed.scheme}://{parsed.netloc}{path}"
    return f"{base}?{parsed.query}" if parsed.query else base