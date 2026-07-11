#!/usr/bin/env python3
"""
Unified Service Starter for Ethical Agents
==========================================

Starts all required services:
1. Backend API (port 8000)
2. Frontend Dev Server (port 5173)
"""

import subprocess
import sys
import time
import platform
from pathlib import Path


IS_WINDOWS = platform.system() == "Windows"


def start_service(name: str, command: list[str], cwd: Path) -> subprocess.Popen:
    """Start a service in the background."""
    print(f"  Starting {name}...")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        # On Windows, use shell=True so npm.cmd and other shell scripts are resolved
        shell=IS_WINDOWS,
    )
    return process


def npm_cmd() -> str:
    """Return the correct npm command for the current OS."""
    return "npm.cmd" if IS_WINDOWS else "npm"


def main():
    base_dir = Path(__file__).parent

    print("=" * 70)
    print("ETHICAL AGENTS - SERVICE STARTER")
    print("=" * 70 + "\n")

    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        # ── Backend API ────────────────────────────────────────────────────
        backend_cmd = [
            sys.executable, "-m", "uvicorn",
            "backend.app.main:app",
            "--reload",
            "--port", "8000",
        ]
        backend_process = start_service("Backend API", backend_cmd, base_dir)
        processes.append(("Backend API", backend_process))
        time.sleep(2)

        # Check it started cleanly
        if backend_process.poll() is not None:
            err = backend_process.stderr.read() if backend_process.stderr else ""
            print(f"\n[ERROR] Backend failed to start:\n{err}")
            sys.exit(1)

        # ── Frontend Dev Server ────────────────────────────────────────────
        # On Windows subprocess needs shell=True for npm/npm.cmd to resolve,
        # so pass the command as a plain string when on Windows.
        if IS_WINDOWS:
            frontend_cmd = "npm run dev"          # string → shell interprets it
        else:
            frontend_cmd = ["npm", "run", "dev"]  # list → no shell needed

        frontend_process = start_service(
            "Frontend Dev Server",
            frontend_cmd,        # type: ignore[arg-type]
            base_dir / "frontend",
        )
        processes.append(("Frontend", frontend_process))
        time.sleep(3)

        if frontend_process.poll() is not None:
            err = frontend_process.stderr.read() if frontend_process.stderr else ""
            print(f"\n[ERROR] Frontend failed to start:\n{err}")
            sys.exit(1)

        print("\n" + "=" * 70)
        print("ALL SERVICES STARTED")
        print("=" * 70)
        print("  Backend API :  http://localhost:8000")
        print("  Frontend    :  http://localhost:3000")
        print("  Health check:  http://localhost:8000/health")
        print("\n  Press Ctrl+C to stop all services")
        print("=" * 70 + "\n")

        # ── Monitor ────────────────────────────────────────────────────────
        while True:
            time.sleep(2)
            for svc_name, proc in processes:
                if proc.poll() is not None:
                    print(f"\n[WARNING] {svc_name} stopped unexpectedly (exit {proc.returncode})")
                    raise KeyboardInterrupt

    except KeyboardInterrupt:
        print("\n\nStopping all services...")
        for svc_name, proc in processes:
            print(f"  Stopping {svc_name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("All services stopped.\n")


if __name__ == "__main__":
    main()
