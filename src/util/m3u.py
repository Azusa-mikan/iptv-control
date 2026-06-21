import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from src.util import is_url, safe_url

@dataclass(slots=True, kw_only=True)
class Channel:
    name: str
    url: str

def parse_m3u(content: str) -> list[Channel]:
    result: list[Channel] = []
    name = None
    for line in content.splitlines():
        line = line.strip()
        m = re.match(r'#EXTINF:-?\d*\s*,?(.*)', line)
        if m:
            name = m.group(1).strip()
        elif line and not line.startswith('#') and name:
            result.append(Channel(name=name, url=line))
            name = None
    return result

def load_local_m3u(path: Path) -> list[Channel]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    content = path.read_text(encoding='utf-8')
    return parse_m3u(content)

def load_online_m3u(url: str) -> list[Channel]:
    try:
        # 发送HTTP请求并设置超时时间，避免长时间挂起
        resp = httpx.get(url, timeout=30.0)
        # 检查响应状态码，非200系列状态码抛出异常
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return parse_m3u(resp.text)
    except httpx.RequestError as e:
        # 处理网络请求相关错误，如连接失败、超时等
        raise RuntimeError(f"Failed to fetch M3U from {url}: Network error - {str(e)}") from e
    except httpx.HTTPStatusError as e:
        # 处理HTTP错误状态码，如404、500等
        raise RuntimeError(f"Failed to fetch M3U from {url}: HTTP error - {str(e)}") from e
    except Exception as e:
        # 处理其他未预期的错误
        raise RuntimeError(f"Unexpected error loading M3U from {url}: {str(e)}") from e

def load_m3u(path: str) -> list[Channel]:
    if is_url(path):
        return load_online_m3u(path)
    else:
        return load_local_m3u(Path(path))