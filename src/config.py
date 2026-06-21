import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

M3U_PATH = os.environ['M3U_PATH']
MPV_PATH: Path | None = (
    Path(v) if (v := os.getenv("MPV_PATH"))
    else Path(p) if (p := shutil.which("mpv"))
    else None
)
