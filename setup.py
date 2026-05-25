import platform
import subprocess
import sys

req = "requirements-macos.txt" if platform.system() == "Darwin" else "requirements-desktop.txt"

print(f"Installing requirements from {req}...")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", req], check=True)

print("Installing Playwright browsers...")
subprocess.run([sys.executable, "-m", "playwright", "install"], check=True)

print("\n✅ Setup complete! Run 'python main.py' to start Raaj-Jarvis.")
