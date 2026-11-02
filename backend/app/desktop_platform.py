"""Optional native tray on Windows/macOS; Linux has a browser/CLI fallback."""
import os
import sys
import webbrowser


def _copy_address(address):
    if sys.platform == 'darwin':
        import subprocess
        subprocess.run(['pbcopy'], input=address, text=True, check=True)
    else:
        # Keep the existing Windows clipboard feature without importing Tk on Linux.
        import tkinter
        clipboard = tkinter.Tk()
        clipboard.withdraw()
        clipboard.clipboard_clear()
        clipboard.clipboard_append(address)
        clipboard.update()
        clipboard.destroy()


def _tray_image():
    from PIL import Image, ImageDraw
    picture = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)
    draw.rounded_rectangle((3, 3, 61, 61), radius=12, fill='#263e5c')
    draw.text((16, 20), 'AT', fill='white')
    return picture


def show_ui(address, server_thread):
    if os.environ.get('APP_DESKTOP_NO_BROWSER') != '1':
        webbrowser.open(address)
    # No X11, tkinter or tray dependency is imported by Linux/headless startup.
    if sys.platform not in {'win32', 'darwin'} or os.environ.get('APP_DESKTOP_HEADLESS') == '1':
        print(f'Application Tracker: {address} (Ctrl+C to stop)', flush=True)
        try:
            while server_thread.is_alive():
                server_thread.join(timeout=0.5)
        except KeyboardInterrupt:
            pass
        return
    import pystray
    icon = pystray.Icon('Application Tracker', _tray_image(), 'Application Tracker', menu=pystray.Menu(
        pystray.MenuItem('Open', lambda *_: webbrowser.open(address), default=True),
        pystray.MenuItem('Status', lambda *_: webbrowser.open(address + '/api/health')),
        pystray.MenuItem('Copy API address', lambda *_: _copy_address(address)),
        pystray.MenuItem('Settings', lambda *_: webbrowser.open(address + '/#/settings')),
        pystray.MenuItem('Exit', lambda icon, _: icon.stop()),
    ))
    icon.run()
