"""Windows tray host for the built tracker UI and local API."""
import threading
import time
import tkinter
import os
import logging
import webbrowser

import uvicorn

from app.config import Settings
from app.main import create_app


def _tray_image():
    from PIL import Image, ImageDraw

    picture = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    draw.rounded_rectangle((3, 3, 61, 61), radius=12, fill="#263e5c")
    draw.text((16, 20), "AT", fill="white")
    return picture


def _copy_address(address: str) -> None:
    clipboard = tkinter.Tk()
    clipboard.withdraw()
    clipboard.clipboard_clear()
    clipboard.clipboard_append(address)
    clipboard.update()
    clipboard.destroy()


def run() -> None:
    import pystray

    settings = Settings()
    if not (settings.app_static_dir / "index.html").is_file():
        raise RuntimeError("Built frontend is missing. Run the frontend build first.")
    if settings.app_host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("The desktop host must bind to the local computer")
    settings.app_data_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=settings.app_data_dir / "desktop.log", level=settings.log_level.upper(), force=True)
    address = f"http://127.0.0.1:{settings.app_port}"
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=settings.app_port, log_level=settings.log_level, log_config=None))
    thread = threading.Thread(target=server.run, name="tracker-api", daemon=True)
    thread.start()
    for _ in range(100):
        if server.started or not thread.is_alive():
            break
        time.sleep(0.1)
    if not server.started:
        raise RuntimeError(f"The local server could not start on {address}")

    def open_page(_icon, _item):
        webbrowser.open(address)

    def open_status(_icon, _item):
        webbrowser.open(address + "/api/health")

    def open_settings(_icon, _item):
        webbrowser.open(address + "/#/settings")

    def copy_address(_icon, _item):
        _copy_address(address)

    def exit_app(icon, _item):
        icon.stop()

    icon = pystray.Icon("Application Tracker", _tray_image(), "Application Tracker", menu=pystray.Menu(
        pystray.MenuItem("Open", open_page, default=True),
        pystray.MenuItem("Status", open_status),
        pystray.MenuItem("Copy API address", copy_address),
        pystray.MenuItem("Settings", open_settings),
        pystray.MenuItem("Exit", exit_app),
    ))
    try:
        if os.environ.get("APP_DESKTOP_NO_BROWSER") != "1":
            webbrowser.open(address)
        icon.run()
    finally:
        server.should_exit = True
        thread.join(timeout=15)


if __name__ == "__main__":
    run()
