"""
Desktop launcher for the Biodiversity Field Survey Platform.

Starts the FastAPI app locally and opens the browser once the service is ready.
Works both in development and in a PyInstaller bundle.
"""

import logging
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path


logger = logging.getLogger("launcher")

LAST_URL_FILE = "last-launch-url.txt"


def get_output_dir():
    """Return the user-visible app directory for logs and helper files."""
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def get_resource_dir():
    """Return the resource directory for code and bundled assets."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_free_port(start=8000, end=8100):
    """Find an available localhost port in the given range."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def wait_for_server(host, port, timeout=60):
    """Block until the local server accepts connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def write_last_url(base_dir, url):
    """Persist the last successful local URL for easy manual reopening."""
    try:
        output_dir = Path(base_dir) / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / LAST_URL_FILE).write_text(url, encoding="utf-8")
    except OSError:
        logger.warning("Could not write launch URL file.")


def configure_logging(base_dir):
    """Log to both console and output/launcher.log."""
    output_dir = Path(base_dir) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "launcher.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logger.info("Launcher log: %s", log_file)


def main():
    output_dir = get_output_dir()
    resource_dir = get_resource_dir()
    backend_dir = os.path.join(resource_dir, "backend")

    if not os.path.isdir(backend_dir):
        backend_dir = resource_dir

    app_data_dir = os.path.join(output_dir, "data")
    os.makedirs(app_data_dir, exist_ok=True)
    os.environ["BIRD_PLATFORM_BACKEND_DIR"] = backend_dir
    os.environ["BIRD_PLATFORM_OUTPUT_DIR"] = output_dir
    os.environ["BIRD_PLATFORM_DATA_DIR"] = app_data_dir

    configure_logging(output_dir)

    os.chdir(backend_dir)
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    host = "127.0.0.1"
    requested_port = os.environ.get("BIRD_PLATFORM_PORT", "").strip()
    port = int(requested_port) if requested_port.isdigit() else find_free_port()
    url = f"http://{host}:{port}"
    write_last_url(output_dir, url)

    logger.info("Biodiversity Field Survey Platform")
    logger.info("Starting local app at %s", url)
    logger.info("If the browser does not open automatically, visit: %s", url)

    def open_browser_when_ready():
        if wait_for_server(host, port, timeout=120):
            if os.environ.get("BIRD_PLATFORM_OPEN_BROWSER", "1").lower() not in {"0", "false", "no"}:
                logger.info("Server is ready. Opening browser...")
                webbrowser.open(url)
            else:
                logger.info("Server is ready. Browser auto-open is disabled.")
        else:
            logger.error("Server did not become ready within 120 seconds.")

    browser_thread = threading.Thread(target=open_browser_when_ready, daemon=True)
    browser_thread.start()

    import uvicorn
    from main import app

    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down app.")
    except Exception as exc:
        logger.error("Launcher failed: %s", exc)
        logger.error("%s", traceback.format_exc())
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
