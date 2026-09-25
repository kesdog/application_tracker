"""Entry point for the Windows executable."""
import ctypes
import os
from pathlib import Path
import traceback

from app.desktop import run


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        error_dir = Path(os.environ.get("APP_DATA_DIR", Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ApplicationTracker"))
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if os.environ.get("APP_DESKTOP_NO_BROWSER") != "1":
            ctypes.windll.user32.MessageBoxW(0, str(exc), "Application Tracker", 0x10)
        raise
