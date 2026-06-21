from contextlib import asynccontextmanager

from fastapi import Body
from fastapi import FastAPI, HTTPException

from src.config import M3U_PATH
from src.util.m3u import load_m3u
from src.mpv_controller import MPVController, MpvError

mpv = MPVController()
channels = load_m3u(M3U_PATH)

@asynccontextmanager
async def lifespan(app: FastAPI):
    mpv.start()
    if not mpv.running.wait(1.0):
        raise MpvError("mpv process not started")
    yield
    mpv.stop()

app = FastAPI(lifespan=lifespan)

@app.get("/channels")
async def channel_list():
    return channels

@app.post("/channels/select")
async def channel_change(name: str = Body(..., embed=True)):
    for channel in channels:
        if channel.name == name:
            ok = await mpv.load(channel.url)
            if ok:
                return {"message": f"switched to {name}"}
            else:
                raise HTTPException(status_code=500, detail="failed to switch channel")
    raise HTTPException(status_code=404, detail="channel not found")
