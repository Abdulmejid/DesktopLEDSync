import subprocess
import sys
import os
import customtkinter as ctk

print("--- Standalone LED Sync Builder ---")
print("Installing build dependencies...")
subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

# Delete old build folders if they exist
print("\nCleaning up old builds...")
if os.path.exists("build"):
    subprocess.run(["rmdir", "/s", "/q", "build"], shell=True)
if os.path.exists("dist"):
    subprocess.run(["rmdir", "/s", "/q", "dist"], shell=True)
if os.path.exists("SyncApp.spec"):
    os.remove("SyncApp.spec")

print("\nPackaging the application...")
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "DesktopLEDSync",
    "--onefile",
    "--noconsole", # Don't show the black DOS command prompt window anymore
    "--add-data", "config.json;.", # Include the config file
    
    # CustomTkinter needs its theme files explicitly bundled in Windows
    "--add-data", f"{os.path.dirname(ctk.__file__)};customtkinter",
    
    "gui.py"
]

subprocess.run(cmd, check=True)

print("\n--- BUILD COMPLETE ---")
print("Your executable is located in the 'dist' folder!")
print("You can double-click 'DesktopLEDSync.exe' to run the app.")
