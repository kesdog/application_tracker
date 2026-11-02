"""Production PWA shell smoke in Chromium/WebKit; never contacts Google."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('frontend/dist'))
    args = parser.parse_args()
    handler = partial(SimpleHTTPRequestHandler, directory=str(args.source.resolve()))
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f'http://127.0.0.1:{server.server_port}'
    try:
        with sync_playwright() as playwright:
            for engine in [playwright.chromium, playwright.webkit]:
                with engine.launch() as browser:
                    context = browser.new_context()
                    # Provider access is a separate operator check with synthetic accounts.
                    context.route('https://**/*', lambda route: route.abort())
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(address + '/phone/')
                    page.get_by_role('heading', name='Your phone workspace').wait_for()
                    page.wait_for_function('navigator.serviceWorker.controller !== null')
                    manifest = page.evaluate("fetch('/phone/manifest.webmanifest').then(r => r.json())")
                    assert manifest['scope'] == '/phone/'
                    # The production worker must preserve encrypted replica storage.
                    page.evaluate("""() => new Promise((resolve, reject) => {
                      const request = indexedDB.open('release-smoke', 1);
                      request.onupgradeneeded = () => request.result.createObjectStore('sentinel');
                      request.onerror = reject;
                      request.onsuccess = () => { const db = request.result;
                        const tx = db.transaction('sentinel', 'readwrite');
                        tx.objectStore('sentinel').put('synthetic encrypted bytes', 'persisted');
                        tx.oncomplete = () => { db.close(); resolve(true); }; };
                    })""")
                    if engine.name == 'webkit':
                        # WebKit's offline emulation rejects even SW responses:
                        # https://github.com/microsoft/playwright/issues/42775
                        # Stop the actual origin instead, exercising its cache fallback.
                        server.shutdown()
                        server.server_close()
                    else:
                        context.set_offline(True)
                    page.reload()
                    page.get_by_role('heading', name='Your phone workspace').wait_for()
                    assert page.evaluate("""() => new Promise(resolve => {
                      const request = indexedDB.open('release-smoke', 1);
                      request.onsuccess = () => { const db = request.result;
                        const tx = db.transaction('sentinel'); const read = tx.objectStore('sentinel').get('persisted');
                        read.onsuccess = () => { db.close(); resolve(read.result); }; };
                    })""") == 'synthetic encrypted bytes'
                    assert errors == [], errors
                    context.close()
                print(f'{engine.name}: production phone shell, service worker, offline reload and IndexedDB preservation passed')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main()
