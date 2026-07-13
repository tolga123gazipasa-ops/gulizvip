import subprocess, time, signal, sys, os

os.chdir("/sessions/tender-wizardly-edison/mnt/gulizvip")
log = open("/sessions/tender-wizardly-edison/mnt/gulizvip/server.log", "w")
proc = subprocess.Popen(
    ["python3", "-u", "server.py"],
    stdout=log,
    stderr=subprocess.STDOUT,
    preexec_fn=os.setsid
)
print(f"Started PID: {proc.pid}")

# Wait for startup
time.sleep(8)
log.flush()

# Check if alive
if proc.poll() is not None:
    print(f"Process exited with code {proc.returncode}")
else:
    print("Process is still running")

# Read log
with open("/sessions/tender-wizardly-edison/mnt/gulizvip/server.log") as f:
    print("--- LOG ---")
    print(f.read())

# Test endpoints
import urllib.request
try:
    r = urllib.request.urlopen("http://localhost:8081/api/unit-price", timeout=5)
    print(f"--- TEST /api/unit-price: {r.status} ---")
    print(r.read().decode()[:200])
except Exception as e:
    print(f"Test failed: {e}")

# Keep alive so caller can curl
print(f"\nServer PID {proc.pid} running. Press Ctrl+C to stop.")
try:
    while True:
        time.sleep(60)
        if proc.poll() is not None:
            print(f"Process died with code {proc.returncode}")
            break
except KeyboardInterrupt:
    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    print("Stopped")
