#!/usr/bin/env python
"""
StoryGame Application Runner
This script starts both frontend and backend servers using the current Python environment.
"""

import os
import sys
import subprocess
import time
import signal
import platform
import atexit
import socket
import argparse
import importlib.util
from pathlib import Path

# Terminal colors for better readability (works on most terminals)
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'  # No Color

# Define ports
BACKEND_PORT = 11454
FRONTEND_PORT = 3000

# For Windows CMD which doesn't support ANSI colors
IS_WINDOWS = platform.system() == "Windows"

def print_colored(text, color):
    """Print colored text if supported by the terminal"""
    if IS_WINDOWS:
        print(text)
    else:
        print(f"{color}{text}{NC}")

def check_python_env():
    """Report which interpreter is being used and warn if it differs from the project venv."""
    current_python = Path(sys.executable).resolve()
    project_root = Path(os.path.dirname(os.path.abspath(__file__)))
    preferred_python = project_root / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")

    print_colored(f"Using Python interpreter: {current_python}", GREEN)
    if preferred_python.exists() and current_python != preferred_python.resolve():
        print_colored(
            f"Warning: this is not the project virtualenv interpreter ({preferred_python}).",
            YELLOW,
        )
        print_colored(
            "Continuing with the current interpreter, but stale processes from a different environment can cause confusing behavior.",
            YELLOW,
        )
    return True


def check_python_dependencies():
    """Warn when the active interpreter is missing packages declared by the project."""
    required_modules = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "openai": "openai",
        "pydantic_settings": "pydantic-settings",
        "requests": "requests",
        "PIL": "Pillow",
        "google.genai": "google-genai",
    }
    missing = [
        package_name
        for module_name, package_name in required_modules.items()
        if importlib.util.find_spec(module_name) is None
    ]
    if not missing:
        return True

    print_colored(
        "Warning: the current Python interpreter is missing project dependencies: "
        + ", ".join(missing),
        YELLOW,
    )
    print_colored(
        f"Install them into this interpreter with: {sys.executable} -m pip install -r requirements.txt",
        YELLOW,
    )
    return True


def find_listening_pids(port):
    """Return the PIDs currently listening on the provided TCP port."""
    pids = set()

    if IS_WINDOWS:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=False,
        )
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 5 or parts[0].upper() != "TCP":
                continue
            local_address = parts[1]
            state = parts[3].upper()
            pid = parts[4]
            if local_address.endswith(f":{port}") and state == "LISTENING" and pid.isdigit():
                pids.add(int(pid))
        return sorted(pids)

    result = subprocess.run(
        ["lsof", "-i", f":{port}", "-sTCP:LISTEN", "-t"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return sorted(pids)


def terminate_pid(pid):
    """Terminate a process by PID, including child processes when possible."""
    if pid == os.getpid():
        print_colored(f"Skipping current launcher process {pid}.", YELLOW)
        return

    if IS_WINDOWS:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return

    subprocess.run(
        ["kill", "-9", str(pid)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

def is_command_available(command):
    """Check if a command is available on the system"""
    if IS_WINDOWS:
        cmd = f"where {command}"
    else:
        cmd = f"which {command}"
    
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return len(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        return False

def check_and_free_port(port):
    """Check if a port is in use and try to kill the process"""
    try:
        # Check if port is in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("0.0.0.0", port))
            # Port is free
            return True
    except OSError:
        print_colored(f"Port {port} is already in use. Attempting to free it...", YELLOW)

        try:
            pids = find_listening_pids(port)
            if not pids:
                print_colored(f"Could not identify the process using port {port}.", RED)
                return False

            print_colored(f"Found listener(s) on port {port}: {', '.join(str(pid) for pid in pids)}", YELLOW)
            for pid in pids:
                terminate_pid(pid)

            for _ in range(10):
                time.sleep(0.5)
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.bind(("0.0.0.0", port))
                        print_colored(f"Port {port} is now free.", GREEN)
                        return True
                except OSError:
                    continue

            remaining = find_listening_pids(port)
            if remaining:
                print_colored(
                    f"Could not free port {port}. Remaining listener(s): {', '.join(str(pid) for pid in remaining)}",
                    RED,
                )
            else:
                print_colored(f"Could not free port {port}. Please close the application using it manually.", RED)
            return False
        except Exception as e:
            print_colored(f"Error when trying to free port {port}: {e}", RED)
            return False

# Store processes to terminate them later
processes = []

def cleanup():
    """Terminate all child processes when the script exits"""
    print_colored("\nShutting down servers...", YELLOW)
    for process in processes:
        if process and process.poll() is None:  # If process exists and is still running
            try:
                if IS_WINDOWS:
                    process.terminate()
                else:
                    process.send_signal(signal.SIGTERM)
            except:
                pass  # Ignore errors during cleanup
    
    print_colored("Cleanup complete. Goodbye!", GREEN)


def parse_args():
    parser = argparse.ArgumentParser(description="Start the StoryGame frontend and backend.")
    parser.add_argument(
        "--random",
        action="store_true",
        help="Enable blind benchmark assignment mode for benchmark sessions.",
    )
    return parser.parse_args()

# Register cleanup function to execute on script exit
atexit.register(cleanup)

def main():
    args = parse_args()
    print_colored("Starting StoryGame Application...", GREEN)
    
    # Check the current Python interpreter/runtime
    if not check_python_env():
        sys.exit(1)
    check_python_dependencies()
    
    # Free ports if they are in use
    if not check_and_free_port(BACKEND_PORT):
        print_colored(f"Could not free backend port {BACKEND_PORT}. Exiting.", RED)
        sys.exit(1)
    
    if not check_and_free_port(FRONTEND_PORT):
        print_colored(f"Could not free frontend port {FRONTEND_PORT}. Exiting.", RED)
        sys.exit(1)
    
    # Get the project root directory
    project_root = Path(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = project_root / "backend"
    frontend_dir = project_root / "frontend"
    
    # Check if directories exist
    if not backend_dir.exists():
        print_colored("Error: backend directory not found", RED)
        sys.exit(1)
    if not frontend_dir.exists():
        print_colored("Error: frontend directory not found", RED)
        sys.exit(1)
    
    # Start backend server
    print_colored("Starting backend server...", GREEN)
    os.chdir(backend_dir)
    
    # Change to src directory
    backend_src_dir = backend_dir / "src"
    if not backend_src_dir.exists():
        print_colored("Error: backend/src directory not found", RED)
        sys.exit(1)
    os.chdir(backend_src_dir)
    
    # Use uvicorn directly instead of `python main.py` so Windows avoids
    # the reload subprocess behavior hardcoded in backend/src/main.py.
    backend_cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(BACKEND_PORT),
    ]
    print_colored(f"Starting FastAPI server on http://localhost:{BACKEND_PORT}", YELLOW)
    backend_env = os.environ.copy()
    if args.random:
        backend_env["BENCHMARK_RANDOM_MODE"] = "1"
    
    # Start backend process
    try:
        backend_process = subprocess.Popen(
            backend_cmd, 
            stdout=subprocess.PIPE if not IS_WINDOWS else None,
            stderr=subprocess.PIPE if not IS_WINDOWS else None,
            text=True,
            env=backend_env,
        )
        processes.append(backend_process)
    except Exception as e:
        print_colored(f"Error starting backend server: {e}", RED)
        sys.exit(1)
    
    # Wait a bit for backend to start
    time.sleep(2)
    if backend_process.poll() is not None:
        print_colored("Error: Backend server failed to start", RED)
        print_colored(f"Exit code: {backend_process.returncode}", RED)
        if backend_process.stderr:
            print_colored(f"Error output: {backend_process.stderr.read()}", RED)
        sys.exit(1)
    
    # Go back to project root
    os.chdir(project_root)
    
    # Start frontend server
    print_colored("Starting frontend server...", GREEN)
    os.chdir(frontend_dir)
    
    # Check for npm or yarn
    frontend_cmd = None
    yarn_cmd = "yarn.cmd" if IS_WINDOWS else "yarn"
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"

    if is_command_available("yarn"):
        frontend_cmd = [yarn_cmd, "start"]
        print_colored("Starting EmoNest with yarn...", YELLOW)
    elif is_command_available("npm"):
        frontend_cmd = [npm_cmd, "start"]
        print_colored("Starting EmoNest with npm...", YELLOW)
    else:
        print_colored("Error: Neither yarn nor npm found. Cannot start frontend.", RED)
        sys.exit(1)
    
    # Start frontend process
    frontend_env = os.environ.copy()
    if args.random:
        frontend_env["REACT_APP_BENCHMARK_RANDOM_MODE"] = "1"
        frontend_env["BENCHMARK_RANDOM_MODE"] = "1"
    try:
        frontend_process = subprocess.Popen(
            frontend_cmd,
            stdout=subprocess.PIPE if not IS_WINDOWS else None,
            stderr=subprocess.PIPE if not IS_WINDOWS else None,
            text=True,
            env=frontend_env,
        )
        processes.append(frontend_process)
    except Exception as e:
        print_colored(f"Error starting frontend server: {e}", RED)
        sys.exit(1)
    
    # Return to project root
    os.chdir(project_root)
    
    # Print success message
    print_colored("\nFrontend will open in your browser shortly...", GREEN)
    print_colored("================================", GREEN)
    print_colored("StoryGame is now running!", GREEN)
    print_colored(f"Frontend: http://localhost:{FRONTEND_PORT}", YELLOW)
    print_colored(f"Backend: http://localhost:{BACKEND_PORT}", YELLOW)
    print_colored("================================", GREEN)
    print_colored("Press Ctrl+C to stop both servers", YELLOW)
    if args.random:
        print_colored("Blind benchmark random mode is enabled.", YELLOW)
    
    try:
        # Keep the script running until Ctrl+C or until processes terminate
        while True:
            if backend_process.poll() is not None:
                print_colored("Backend server has stopped", RED)
                break
            if frontend_process.poll() is not None:
                print_colored("Frontend server has stopped", RED)
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt")
    finally:
        cleanup()

if __name__ == "__main__":
    main() 
