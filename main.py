"""
Launcher único: sobe o backend Python e abre o Electron.
Rode com: python main.py
"""
import subprocess
import sys
import time
import os
import signal
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

def start_backend() -> subprocess.Popen:
    """Sobe o FastAPI como subprocesso."""
    print("🚀 Iniciando backend...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND,
    )
    # Espera o servidor responder antes de abrir a UI
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
            print("✅ Backend pronto em http://127.0.0.1:8000")
            return proc
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("Backend não respondeu em 9s")

def start_frontend() -> subprocess.Popen:
    """Abre a janela do Electron."""
    print("🖥️  Abrindo frontend...")
    # No Windows usa npm.cmd, no Linux/Mac usa npm
    npm = "npm.cmd" if os.name == "nt" else "npm"
    return subprocess.Popen([npm, "start"], cwd=FRONTEND)

def main():
    backend_proc = None
    frontend_proc = None
    try:
        backend_proc = start_backend()
        frontend_proc = start_frontend()

        # Fica vivo até o frontend (Electron) fechar
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\n⏹️  Encerrando...")
    finally:
        # Ao fechar o frontend, mata o backend
        if backend_proc and backend_proc.poll() is None:
            print("🛑 Encerrando backend...")
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_proc.kill()

if __name__ == "__main__":
    main()