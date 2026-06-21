import re
from typing import  NamedTuple
from pathlib import Path

import httpx

class Channel(NamedTuple):
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
    content = path.read_text(encoding='utf-8')
    return parse_m3u(content)

def load_online_m3u(url: str) -> list[Channel]:
    resp = httpx.get(url)
    resp.encoding = "utf-8"
    return parse_m3u(resp.text)



