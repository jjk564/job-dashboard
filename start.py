import subprocess
import sys
import time
import os
import webbrowser
import socket
import atexit
import urllib.request

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0


def is_port_in_use(port: int) -> bool:
    """Check if a local port is accepting TCP connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_http_healthy(url: str, timeout: float = 3.0) -> bool:
    """Verify the HTTP server actually responds on the given URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JobPulse-Watchdog/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def free_port(port: int):
    """Clean up any stale process holding the port on Windows."""
    if not is_port_in_use(port):
        return
    print(f"[*] Port {port} is currently in use. Releasing stale process...")
    try:
        if os.name == "nt":
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
            pids = set()
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts:
                    pid = parts[-1]
                    if pid != "0":
                        pids.add(pid)
            for pid in pids:
                subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True)
                subprocess.run(
                    f'powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object {{ $_.ParentProcessId -eq {pid} -or $_.CommandLine -like \'*parent_pid={pid}*\' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"',
                    shell=True,
                    capture_output=True,
                )
            time.sleep(1)
    except Exception as e:
        print(f"    Notice: Port {port} cleanup: {e}")


def kill_proc_tree(proc):
    """Cleanly terminate a process and all its child workers."""
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.terminate()
    except Exception:
        pass


def start_backend(backend_dir: str):
    return subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=backend_dir,
        creationflags=CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_frontend(frontend_dir: str, npm_cmd: str):
    return subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
        creationflags=CREATE_NEW_PROCESS_GROUP,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_windows_startup(root_dir: str):
    """
    Registers a lightweight VBS startup script in the current user's Windows Startup folder
    so JobPulse Watchdog starts automatically in the background on Windows login.
    """
    if os.name != "nt":
        return
    try:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return
        startup_dir = os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        if not os.path.isdir(startup_dir):
            return
        vbs_path = os.path.join(startup_dir, "JobPulse_AlwaysOn.vbs")
        python_exe = sys.executable
        pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
        runner_exe = pythonw_exe if os.path.exists(pythonw_exe) else python_exe
        start_py = os.path.join(root_dir, "start.py")

        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.CurrentDirectory = "{root_dir}"\n'
            f'WshShell.Run """{runner_exe}"" ""{start_py}"" --no-browser --ensure-running --no-kill-on-exit", 0, False\n'
        )
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)
        print(f"[OK] Registered Windows Startup Always-On launcher: {vbs_path}")
    except Exception as e:
        print(f"[*] Could not register Windows Startup launcher: {e}")



def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))

    # Redirect logging to watchdog.log if run in windowless pythonw mode
    if sys.stdout is None or getattr(sys.stdout, "closed", False):
        try:
            log_f = open(os.path.join(root_dir, "watchdog.log"), "a", encoding="utf-8", buffering=1)
            sys.stdout = log_f
            sys.stderr = log_f
        except Exception:
            pass
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

    ensure_windows_startup(root_dir)

    if "--spawn-detached" in sys.argv:
        # Spawn start.py as an independent detached background process that survives shell exit
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        flags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW if os.name == "nt" else 0
        log_path = os.path.join(root_dir, "watchdog.log")
        log_file = open(log_path, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, os.path.join(root_dir, "start.py"), "--no-browser", "--no-kill-on-exit"],
            cwd=root_dir,
            stdout=log_file,
            stderr=log_file,
            creationflags=flags,
            close_fds=True if os.name != "nt" else False,
        )
        print(f"[*] Spawned detached Always-On JobPulse Watchdog (PID: {proc.pid})")
        for _ in range(30):
            time.sleep(0.5)
            if is_http_healthy("http://127.0.0.1:8000/api/health") and is_port_in_use(5173):
                print("[OK] Backend (http://127.0.0.1:8000) and Frontend (http://localhost:5173) are ONLINE!")
                return
        print("[*] Watchdog is initializing services in the background...")
        return

    print("=" * 60)
    print("   Starting JobPulse: Always-On Watchdog & Local Copilot   ")
    print("=" * 60)

    # If already healthy and --ensure-running is passed, reuse existing servers
    if "--ensure-running" in sys.argv and is_http_healthy("http://127.0.0.1:8000/api/health") and is_port_in_use(5173):
        print("[OK] JobPulse Backend (8000) and Frontend (5173) are already healthy. Entering watchdog monitor...")
        backend_proc = None
        frontend_proc = None
    else:
        free_port(8000)
        free_port(5173)

        print("[1/3] Starting FastAPI backend on http://127.0.0.1:8000...")
        backend_proc = start_backend(backend_dir)

        print("[2/3] Starting Vite frontend on http://localhost:5173...")
        frontend_proc = start_frontend(frontend_dir, npm_cmd)

    def cleanup():
        if "--no-kill-on-exit" in sys.argv or "--ensure-running" in sys.argv:
            return
        print("\nStopping JobPulse services...")
        kill_proc_tree(backend_proc)
        kill_proc_tree(frontend_proc)
        print("All JobPulse services stopped.")

    atexit.register(cleanup)

    print("[3/3] Waiting for services to initialize...")
    for _ in range(30):
        time.sleep(0.5)
        if is_port_in_use(8000) and is_port_in_use(5173):
            break

    print("\nJobPulse is active and monitored by Always-On Watchdog!")
    print(" - Dashboard:   http://localhost:5173")
    print(" - Backend API: http://127.0.0.1:8000/docs")
    print(" - Watchdog:    Auto-restarts Backend or Frontend on crash or health check failure\n")

    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open("http://localhost:5173")
        except Exception:
            pass

    backend_fail_streak = 0
    frontend_fail_streak = 0

    try:
        while True:
            time.sleep(3)

            # 1. Verify Backend process & TCP listening port health
            # (Uses OS-level TCP port check so long-running scraping or Playwright tasks never trigger a false kill)
            proc_dead = backend_proc is not None and backend_proc.poll() is not None
            port_ok = is_port_in_use(8000)
            if proc_dead or not port_ok:
                backend_fail_streak += 1
                if proc_dead or backend_fail_streak >= 4:
                    print(f"[!] Watchdog: Backend unhealthy (proc_dead={proc_dead}, streak={backend_fail_streak}). Restarting backend...")
                    kill_proc_tree(backend_proc)
                    free_port(8000)
                    backend_proc = start_backend(backend_dir)
                    backend_fail_streak = 0
                    time.sleep(2)
            else:
                backend_fail_streak = 0

            # 2. Verify Frontend process & TCP/HTTP health
            fe_dead = frontend_proc is not None and frontend_proc.poll() is not None
            fe_ok = is_port_in_use(5173)
            if fe_dead or not fe_ok:
                frontend_fail_streak += 1
                if fe_dead or frontend_fail_streak >= 3:
                    print(f"[!] Watchdog: Frontend unhealthy (fe_dead={fe_dead}, streak={frontend_fail_streak}). Restarting frontend...")
                    kill_proc_tree(frontend_proc)
                    free_port(5173)
                    frontend_proc = start_frontend(frontend_dir, npm_cmd)
                    frontend_fail_streak = 0
                    time.sleep(2)
            else:
                frontend_fail_streak = 0

    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
