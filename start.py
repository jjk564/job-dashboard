import subprocess
import sys
import time
import os
import webbrowser

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dir = os.path.join(root_dir, "frontend")

    print("=" * 60)
    print("   Starting JobPulse: Local Job Dashboard & Copilot   ")
    print("=" * 60)

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

    # Wait 2 seconds and open browser
    time.sleep(2)
    print("[3/3] Opening dashboard in browser: http://localhost:5173")
    try:
        webbrowser.open("http://localhost:5173")
    except Exception:
        pass

    print("\nJobPulse is active!")
    print(" - Backend API: http://127.0.0.1:8000/docs")
    print(" - Frontend Dashboard: http://localhost:5173")
    print("Press Ctrl+C to stop both servers.\n")

    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nStopping JobPulse services...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Done.")

if __name__ == "__main__":
    main()
