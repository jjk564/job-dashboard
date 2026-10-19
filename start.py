import subprocess
import sys
import time
import os
import webbrowser
import socket
import atexit

def is_port_in_use(port: int) -> bool:
    """Check if a local port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

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
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
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

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")

    print("=" * 60)
    print("   Starting JobPulse: Local Job Dashboard & Copilot   ")
    print("=" * 60)

    # Free up ports if previous instances left stale background processes
    free_port(8000)
    free_port(5173)

    # 1. Start Backend
    print("[1/3] Starting FastAPI backend on http://127.0.0.1:8000...")
    backend_proc = subprocess.Popen(
        [sys.executable, "run.py"],
        cwd=backend_dir,
    )

    # 2. Start Frontend
    print("[2/3] Starting Vite frontend on http://localhost:5173...")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=frontend_dir,
    )

    def cleanup():
        print("\nStopping JobPulse services...")
        kill_proc_tree(backend_proc)
        kill_proc_tree(frontend_proc)
        print("All JobPulse services stopped.")

    atexit.register(cleanup)

    # Wait up to 5 seconds for frontend to become responsive, then open browser
    print("[3/3] Waiting for services to initialize...")
    for _ in range(15):
        time.sleep(0.5)
        if is_port_in_use(5173):
            break

    print("\nJobPulse is active!")
    print(" - Dashboard:   http://localhost:5173")
    print(" - Backend API: http://127.0.0.1:8000/docs")
    print("Press Ctrl+C to stop both servers.\n")

    try:
        webbrowser.open("http://localhost:5173")
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
            # Check if either process died unexpectedly
            if backend_proc.poll() is not None:
                print(f"Backend exited with code {backend_proc.poll()}")
                break
            if frontend_proc.poll() is not None:
                print(f"Frontend exited with code {frontend_proc.poll()}")
                break
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
