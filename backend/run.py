import os
import sys
import uvicorn
import uvicorn.supervisors.basereload as basereload
from uvicorn._subprocess import get_subprocess

# Ensure current directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)


def _win_safe_restart(self: basereload.BaseReload) -> None:
    """
    Terminate only the worker child process without calling
    os.kill(pid, signal.CTRL_C_EVENT), which on Windows broadcasts CTRL_C_EVENT
    to the entire console group (killing start.py, start.bat, and Vite).
    """
    if self.process and self.process.is_alive():
        self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)

    self.process = get_subprocess(
        config=self.config,
        target=self.target,
        sockets=self.sockets,
    )
    self.process.start()


def _win_safe_shutdown(self: basereload.BaseReload) -> None:
    """Cleanly terminate the worker child process and close sockets on shutdown."""
    self.should_exit.set()
    if self.process and self.process.is_alive():
        self.process.terminate()
        self.process.join(timeout=5)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)

    for sock in self.sockets:
        sock.close()


if sys.platform == "win32":
    basereload.BaseReload.restart = _win_safe_restart
    basereload.BaseReload.shutdown = _win_safe_shutdown


if __name__ == "__main__":
    app_dir = os.path.join(BASE_DIR, "app")
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[app_dir],
        reload_excludes=["*.db", "*.db-*", "__pycache__", "*.pyc"],
    )
