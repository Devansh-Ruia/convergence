"""
Demo mode launcher with auto-open browser.
Run with: python scripts/run_demo_mode.py
"""

import subprocess
import time
import webbrowser
import sys

def main():
    print("🚀 Starting Convergence in Demo Mode...")
    print("="*50)
    
    # Start server
    print("\n📡 Starting server...")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    
    # Wait for server to start
    print("⏳ Waiting for server to start...")
    time.sleep(3)
    
    # Open browser
    print("🌐 Opening dashboard in browser...")
    webbrowser.open("http://localhost:8000/dashboard")
    
    print("\n" + "="*50)
    print("✅ Convergence is running!")
    print("📊 Dashboard: http://localhost:8000/dashboard")
    print("📚 API Docs:  http://localhost:8000/docs")
    print("="*50)
    print("\nPress Ctrl+C to stop the server.\n")
    
    try:
        # Stream server output
        for line in server.stdout:
            print(line.decode(), end='')
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
        server.terminate()
        server.wait()
        print("✅ Server stopped.")

if __name__ == "__main__":
    main()