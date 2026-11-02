"""Entry point for native desktop executables and isolated recovery."""
import os
from pathlib import Path
import traceback
import sys

if __name__ == "__main__":
    try:
        import argparse
        parser = argparse.ArgumentParser(description='Application Tracker desktop and recovery')
        parser.add_argument('--data-dir', type=Path)
        parser.add_argument('--restore-backup', type=Path)
        parser.add_argument('--headless', action='store_true', help='Use the foreground browser/CLI host')
        args = parser.parse_args()
        if args.data_dir:
            os.environ['APP_DATA_DIR'] = str(args.data_dir.resolve())
        if args.headless:
            os.environ['APP_DESKTOP_HEADLESS'] = '1'
        if args.restore_backup:
            if not args.data_dir:
                raise ValueError('Recovery requires --data-dir pointing to a new empty directory')
            from app.backup import restore_bundle
            restore_bundle(args.restore_backup, args.data_dir)
            (args.data_dir / 'recovery-success.txt').write_text('Recovery complete. Launch ApplicationTracker.exe --data-dir "' + str(args.data_dir.resolve()) + '"\n', encoding='utf-8')
        else:
            from app.desktop import run
            run()
    except Exception as exc:
        from app.config import desktop_data_dir
        error_dir = Path(os.environ.get('APP_DATA_DIR', desktop_data_dir()))
        error_dir.mkdir(parents=True, exist_ok=True)
        (error_dir / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        if sys.platform == 'win32' and os.environ.get("APP_DESKTOP_NO_BROWSER") != "1":
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(exc), "Application Tracker", 0x10)
        if os.environ.get('APP_DESKTOP_SMOKE') == '1':
            raise SystemExit(1) from None
        raise
