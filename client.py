import os

import httpx
import questionary
from dotenv import load_dotenv

load_dotenv()

API_URL = os.environ["API_URL"]


def get_channels():
    response = httpx.get(f"{API_URL}/channels")
    return response.json()


def switch_channel(name: str) -> str:
    response = httpx.post(f"{API_URL}/channels/select", json={"name": name})
    content = response.json()
    if response.is_error:
        raise RuntimeError(content.get("detail", "unknown error"))
    return content["message"]


def stop_playback() -> str:
    response = httpx.post(f"{API_URL}/channels/stop")
    content = response.json()
    if response.is_error:
        raise RuntimeError(content.get("detail", "unknown error"))
    return content["message"]


def main():
    while True:
        channels = get_channels()
        if not channels:
            questionary.print("no channels available")
            break

        choices = [*[c["name"] for c in channels], "stop playback"]
        selected = questionary.select("select a channel:", choices=choices).ask()

        if selected is None:
            break

        try:
            if selected == "stop playback":
                message = stop_playback()
            else:
                message = switch_channel(selected)
            questionary.print(message)
        except RuntimeError as e:
            questionary.print(f"error: {e}")

        action = questionary.select("", choices=["continue", "exit"]).ask()
        if action == "exit":
            break


if __name__ == "__main__":
    main()