import customtkinter as ctk
from tkinter import colorchooser, messagebox
import json
import os
import threading
import sys
import subprocess
import queue
import ctypes
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import winshell
import win32com.client

# Configure the modern look of the window
ctk.set_appearance_mode("System")  # Follows Windows Dark/Light mode
ctk.set_default_color_theme("blue")

# Safely determine the config path whether running from terminal or PyInstaller .exe
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(application_path, "config.json")

class DesktopLEDSyncGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Desktop LED Sync")
        self.geometry("520x720")
        self.resizable(False, False)

        # Intercept the 'X' close button to hide the window instead
        self.protocol('WM_DELETE_WINDOW', self.hide_window)

        # Load existing config or defaults
        self.config = self.load_config()

        # Title Label
        self.title_label = ctk.CTkLabel(self, text="Desktop LED Sync", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(pady=(20, 5))

        self.subtitle_label = ctk.CTkLabel(self, text="Sync Windows Media to Smart Lights", text_color="gray")
        self.subtitle_label.pack(pady=(0, 20))

        # --- Settings Frame (Scrollable so it always fits on screen) ---
        self.settings_frame = ctk.CTkScrollableFrame(self, height=500)
        self.settings_frame.pack(pady=10, padx=20, fill="x")

        # 1. Light Provider Dropdown
        prov_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        prov_label_frame.pack(pady=(20, 0), padx=20, fill="x")
        self.provider_label = ctk.CTkLabel(prov_label_frame, text="Light Brand / Provider:", anchor="w")
        self.provider_label.pack(side="left")
        self.create_help_button(prov_label_frame, "Light Brand", 
            "Select the brand of your LED strip.\nTapo: Official TP-Link Tapo lights.\nWLED: Custom ESP8266/ESP32 WLED controllers.").pack(side="left", padx=5)
        
        # We will parse the providers folder automatically in the future, but for now hardcode
        self.provider_var = ctk.StringVar(value=self.config.get("provider", "tapo"))
        self.provider_dropdown = ctk.CTkOptionMenu(self.settings_frame, values=["tapo", "wled"], variable=self.provider_var)
        self.provider_dropdown.pack(pady=(5, 15), padx=20, fill="x")

        # 2. IP Address
        ip_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        ip_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.ip_label = ctk.CTkLabel(ip_label_frame, text="LED Strip IP Address:", anchor="w")
        self.ip_label.pack(side="left")
        self.create_help_button(ip_label_frame, "IP Address Help", 
            "For Tapo: Open Tapo App -> Device Settings -> Device Info -> IP Address (e.g. 192.168.1.100).\n\nFor WLED: Look in your router's connected devices, or use the WLED app.").pack(side="left", padx=5)
        
        self.ip_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="e.g. 192.168.1.100")
        self.ip_entry.insert(0, self.config.get("ip_address", ""))
        self.ip_entry.pack(pady=(5, 15), padx=20, fill="x")

        # 3. Username / Email (For Tapo etc)
        user_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        user_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.user_label = ctk.CTkLabel(user_label_frame, text="Tapo Account Email:", anchor="w")
        self.user_label.pack(side="left")
        self.create_help_button(user_label_frame, "Account Email", 
            "Enter the email address used for your Tapo account. This is required for local authentication.\n(Leave blank if using WLED)").pack(side="left", padx=5)
        
        self.user_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="Leave blank for WLED")
        self.user_entry.insert(0, self.config.get("credentials", {}).get("username", ""))
        self.user_entry.pack(pady=(5, 15), padx=20, fill="x")

        # 4. Password
        pass_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        pass_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.pass_label = ctk.CTkLabel(pass_label_frame, text="Tapo Account Password:", anchor="w")
        self.pass_label.pack(side="left")
        self.create_help_button(pass_label_frame, "Account Password", 
            "Enter your Tapo account password.\n(Leave blank if using WLED)").pack(side="left", padx=5)
        
        self.pass_entry = ctk.CTkEntry(self.settings_frame, show="*", placeholder_text="Leave blank for WLED")
        self.pass_entry.insert(0, self.config.get("credentials", {}).get("password", ""))
        self.pass_entry.pack(pady=(5, 10), padx=20, fill="x")

        # 4b. Save & Apply Button
        self.apply_btn = ctk.CTkButton(
            self.settings_frame, text="\uE74E Save & Apply", 
            fg_color="#1a5a8a", hover_color="#134466",
            command=self.refresh_sync
        )
        self.apply_btn.pack(pady=(0, 20), padx=20, fill="x")

        # 5. Idle Behavior
        idle_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        idle_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.idle_label = ctk.CTkLabel(idle_label_frame, text="When Music Pauses:", anchor="w")
        self.idle_label.pack(side="left")
        self.create_help_button(idle_label_frame, "Idle Behavior", 
            "Default Color: Switch to a specific solid color when music stops.\nTurn Off: Power off the lights entirely.\nDo Nothing: Keep the lights displaying the very last album art color.").pack(side="left", padx=5)
        
        # Handle migration from old snake_case values
        old_val = self.config.get("settings", {}).get("idle_behavior", "Default Color")
        val_map = {"default_color": "Default Color", "turn_off": "Turn Off", "do_nothing": "Do Nothing"}
        old_val = val_map.get(old_val, old_val)
        
        self.idle_var = ctk.StringVar(value=old_val)
        self.idle_dropdown = ctk.CTkOptionMenu(
            self.settings_frame, 
            values=["Default Color", "Turn Off", "Do Nothing"], 
            variable=self.idle_var,
            command=self.on_idle_behavior_change
        )
        self.idle_dropdown.pack(pady=(5, 10), padx=20, fill="x")

        # 6. Idle Color row (entry + color picker button side by side)
        self.idle_color_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.idle_color_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.idle_color_label = ctk.CTkLabel(self.idle_color_label_frame, text="Idle Color:", anchor="w")
        self.idle_color_label.pack(side="left")
        self.create_help_button(self.idle_color_label_frame, "Idle Color", 
            "The color your lights will revert to when playback stops.\nValues are RGB (Red, Green, Blue) from 0-255.").pack(side="left", padx=5)

        self.idle_color_row_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.idle_color_row_frame.pack(pady=(5, 10), padx=20, fill="x")

        self.idle_color_entry = ctk.CTkEntry(self.idle_color_row_frame, placeholder_text="255,200,100")
        saved_color = self.config.get("settings", {}).get("idle_color", [255, 200, 100])
        self.idle_color_entry.insert(0, f"{saved_color[0]},{saved_color[1]},{saved_color[2]}")
        self.idle_color_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.color_pick_btn = ctk.CTkButton(
            self.idle_color_row_frame, text="\uE790 Pick", width=80,
            command=self.open_color_picker
        )
        self.color_pick_btn.pack(side="left")

        # Apply initial visibility based on saved idle_behavior
        self.after(10, lambda: self.on_idle_behavior_change(self.idle_var.get()))

        # 7. Close Behavior
        close_bh_label_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        close_bh_label_frame.pack(pady=(5, 0), padx=20, fill="x")
        self.close_bh_label = ctk.CTkLabel(close_bh_label_frame, text="When Closing App:", anchor="w")
        self.close_bh_label.pack(side="left")
        self.create_help_button(close_bh_label_frame, "Close Behavior", 
            "Ask what to do: Show a prompt to select minimize or exit.\nMinimize to Tray: Keep syncing in background.\nExit App: Completely quit the program.").pack(side="left", padx=5)
        
        self.close_bh_var = ctk.StringVar(value=self.config.get("settings", {}).get("close_behavior", "Ask what to do"))
        self.close_bh_dropdown = ctk.CTkOptionMenu(
            self.settings_frame, 
            values=["Ask what to do", "Minimize to Tray", "Exit App"], 
            variable=self.close_bh_var,
            command=lambda _: self.save_settings()
        )
        self.close_bh_dropdown.pack(pady=(5, 10), padx=20, fill="x")

        # 8. Match Album Art Brightness
        self.match_brightness_var = ctk.BooleanVar(value=self.config.get("settings", {}).get("match_brightness", False))
        self.match_brightness_switch = ctk.CTkSwitch(
            self.settings_frame,
            text="Match album art brightness",
            variable=self.match_brightness_var,
            command=self.save_settings
        )
        self.match_brightness_switch.pack(pady=(5, 5), padx=20, fill="x")

        # 9. Start With Windows Toggle
        self.autostart_var = ctk.BooleanVar(value=self.check_if_autostart_enabled())
        self.autostart_switch = ctk.CTkSwitch(
            self.settings_frame, text="Run in background when PC starts", 
            variable=self.autostart_var, command=self.save_settings
        )
        self.autostart_switch.pack(pady=(10, 10), padx=20, fill="x")

        # --- Action Buttons (two separate rows) ---
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(10, 2), padx=20, fill="x")

        self.start_button = ctk.CTkButton(btn_row, text="\uE768 Start Syncing",
                                          fg_color="#2d7a2d", hover_color="#1f5c1f",
                                          command=self.toggle_sync)
        self.start_button.pack(side="left", fill="x", expand=True)

        # Hint label
        ctk.CTkLabel(self, text="💡 Network settings require Apply, others save instantly",
                     text_color="gray", font=ctk.CTkFont(size=11)).pack(pady=(0, 4))

        self.stop_event = None  # Will hold a threading.Event when running

        # --- Status Bar ---
        status_row = ctk.CTkFrame(self, fg_color="transparent")
        status_row.pack(pady=(0, 5), padx=20, fill="x")

        self.status_dot = ctk.CTkLabel(status_row, text="●", text_color="gray", width=20)
        self.status_dot.pack(side="left")
        self.status_text = ctk.CTkLabel(status_row, text="Not running", text_color="gray", anchor="w")
        self.status_text.pack(side="left", padx=(4, 0))

        # --- Log Panel ---
        self.log_box = ctk.CTkTextbox(self, height=120, state="disabled", wrap="word")
        self.log_box.pack(pady=(0, 15), padx=20, fill="x")
        self.log_box.tag_config("error", foreground="#ff6b6b")
        self.log_box.tag_config("ok", foreground="#6bff8e")
        self.log_box.tag_config("info", foreground="#aaaaaa")

        # Thread-safe queue for log messages from core engine
        self.log_queue = queue.Queue()

    def load_config(self):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return {"provider": "tapo", "ip_address": "", "credentials": {}, "settings": {}}

    def create_help_button(self, parent, title, message):
        """Helper to create a small '?' button that shows a messagebox."""
        return ctk.CTkButton(
            parent, text="?", width=20, height=20, corner_radius=10,
            fg_color="gray", hover_color="darkgray",
            command=lambda: messagebox.showinfo(title, message)
        )

    def check_if_autostart_enabled(self):
        """Check if shortcut exists in user's startup folder"""
        startup_dir = winshell.startup()
        lnk_path = os.path.join(startup_dir, "DesktopLEDSyncGUI.lnk")
        return os.path.exists(lnk_path)

    def manage_autostart(self):
        """Create or remove Windows startup shortcut based on toggle"""
        startup_dir = winshell.startup()
        lnk_path = os.path.join(startup_dir, "DesktopLEDSyncGUI.lnk")
        
        if self.autostart_var.get():
            # If we are a compiled EXE, point the shortcut to sys.executable
            # If running from python, point to sys.executable "gui.py"
            target = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
            
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(lnk_path)
            if getattr(sys, 'frozen', False):
                shortcut.Targetpath = target
                shortcut.WorkingDirectory = os.path.dirname(target)
            else:
                shortcut.Targetpath = sys.executable
                shortcut.Arguments = f'"{target}"'
                shortcut.WorkingDirectory = os.path.dirname(target)
            shortcut.save()
            print(f"Added Auto-Start shortcut to {lnk_path}")
        else:
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
                print("Removed Auto-Start shortcut.")

    def open_color_picker(self):
        """Open the native Windows color picker and populate the entry."""
        # Build initial color tuple from whatever is currently in the entry
        try:
            parts = [int(x) for x in self.idle_color_entry.get().replace(" ", "").split(",")]
            initial = f"#{parts[0]:02x}{parts[1]:02x}{parts[2]:02x}"
        except Exception:
            initial = "#ffcc64"
        
        result = colorchooser.askcolor(color=initial, title="Choose Idle Light Color")
        if result and result[0]:
            r, g, b = (int(c) for c in result[0])
            self.idle_color_entry.delete(0, "end")
            self.idle_color_entry.insert(0, f"{r},{g},{b}")
            self.save_settings()

    def on_idle_behavior_change(self, value):
        """Show the idle color picker only when 'Default Color' is selected."""
        if value == "Default Color":
            self.idle_color_label_frame.pack(pady=(5, 0), padx=20, fill="x",
                                       before=self.match_brightness_switch)
            self.idle_color_row_frame.pack(pady=(5, 10), padx=20, fill="x",
                                           before=self.match_brightness_switch)
        else:
            self.idle_color_label_frame.pack_forget()
            self.idle_color_row_frame.pack_forget()
        self.save_settings()

    def save_settings(self):
        """Save all GUI fields to config.json. Works while syncing is running."""
        self.config["provider"] = self.provider_var.get()
        self.config["ip_address"] = self.ip_entry.get()

        user = self.user_entry.get()
        pwd = self.pass_entry.get()
        if user or pwd:
            self.config["credentials"] = {"username": user, "password": pwd}
        else:
            self.config["credentials"] = {}

        if "settings" not in self.config:
            self.config["settings"] = {}

        self.config["settings"]["idle_behavior"] = self.idle_var.get()
        self.config["settings"]["match_brightness"] = self.match_brightness_var.get()
        self.config["settings"]["close_behavior"] = self.close_bh_var.get()
        raw_color_str = self.idle_color_entry.get().replace(" ", "")
        try:
            self.config["settings"]["idle_color"] = [int(x) for x in raw_color_str.split(',')]
        except Exception:
            self.config["settings"]["idle_color"] = [255, 200, 100]

        with open(CONFIG_PATH, "w") as f:
            json.dump(self.config, f, indent=2)

        self.manage_autostart()
        self.append_log("Settings saved.", "info")

    def toggle_sync(self):
        """Start the sync engine, or stop it if already running."""
        if self.stop_event is None or self.stop_event.is_set():
            # Not running — start the engine
            self.save_settings()
            self.stop_event = threading.Event()
            self.start_button.configure(text="\uE71A Stop Syncing", fg_color="#7a2d2d", hover_color="#5c1f1f")
            self.set_status("Connecting...", "#f0a500")
            self.append_log("Connecting to device...", "info")
            self.after(300, self.poll_logs)
            threading.Thread(target=self.launch_core, daemon=True).start()
        else:
            # Running — stop the engine
            self.stop_event.set()
            self.start_button.configure(text="\uE768 Start Syncing", fg_color="#2d7a2d", hover_color="#1f5c1f")
            self.set_status("Stopped", "gray")
            self.append_log("Syncing stopped.", "info")

    def refresh_sync(self):
        """Save settings and restart the engine if it was running."""
        self.save_settings()
        was_running = self.stop_event is not None and not self.stop_event.is_set()
        if was_running:
            # Stop the engine, then restart after a short delay
            self.stop_event.set()
            self.set_status("Restarting...", "#f0a500")
            self.append_log("Refreshing — restarting engine with new settings...", "info")
            self.after(1500, self._restart_after_refresh)
        else:
            self.append_log("Settings saved. Press ▶ Start to begin syncing.", "info")

    def _restart_after_refresh(self):
        """Called after stop_event has had time to cleanly exit the loop."""
        self.stop_event = threading.Event()
        self.start_button.configure(text="\uE71A Stop Syncing", fg_color="#7a2d2d", hover_color="#5c1f1f")
        self.after(300, self.poll_logs)
        threading.Thread(target=self.launch_core, daemon=True).start()


    def set_status(self, text, color):
        """Update the status dot and label safely from any thread."""
        self.status_dot.configure(text_color=color)
        self.status_text.configure(text=text, text_color=color)

    def append_log(self, message, tag="info"):
        """Append a colored line to the log textbox."""
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n", tag)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def poll_logs(self):
        """Drain the log queue and update the UI. Re-schedules itself every 300ms."""
        try:
            while True:
                level, message = self.log_queue.get_nowait()
                if level == "ok":
                    self.set_status(message, "#6bff8e")
                    self.append_log("✔ " + message, "ok")
                elif level == "error":
                    self.set_status("Error — see log", "#ff6b6b")
                    self.append_log("✖ " + message, "error")
                else:
                    self.append_log("  " + message, "info")
        except queue.Empty:
            pass
        # Re-schedule as long as the app is open
        self.after(300, self.poll_logs)

    def launch_core(self):
        import core
        import asyncio

        # Inject the shared queue and stop event so core can communicate back to the GUI
        core.log_queue = self.log_queue
        core.stop_event = self.stop_event

        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(core.main())
        except Exception as e:
            self.log_queue.put(("error", f"Core engine crashed: {e}"))
        finally:
            # Reset button back to Start state
            self.after(0, lambda: self.start_button.configure(
                text="\uE768 Start Syncing", fg_color="#2d7a2d", hover_color="#1f5c1f"
            ))
            self.after(0, lambda: self.set_status("Stopped", "gray"))

    # --- System Tray Logic ---
    def create_image(self):
        # Generate a simple 64x64 colored square icon dynamically for the tray
        image = Image.new('RGB', (64, 64), color=(50, 150, 255))
        dc = ImageDraw.Draw(image)
        dc.rectangle((16, 16, 48, 48), fill=(255, 255, 255))
        return image

    def hide_window(self):
        """Ask the user what to do when the X button is pressed."""
        behavior = self.config.get("settings", {}).get("close_behavior", "Ask what to do")
        if behavior == "Minimize to Tray":
            self._do_minimize_to_tray()
            return
        elif behavior == "Exit App":
            self.quit()
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Close")
        dialog.geometry("300x170")
        dialog.resizable(False, False)
        dialog.grab_set()  # Modal — blocks the main window

        # Center over parent
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 300) // 2
        y = self.winfo_y() + (self.winfo_height() - 170) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(dialog, text="What would you like to do?",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(18, 8))

        # Checkbox
        remember_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(dialog, text="Remember my choice", variable=remember_var, font=ctk.CTkFont(size=11)).pack(pady=(0, 10))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 14), padx=20, fill="x")

        def minimize():
            if remember_var.get():
                self.close_bh_var.set("Minimize to Tray")
                self.save_settings()
            dialog.destroy()
            self._do_minimize_to_tray()

        def exit_app():
            if remember_var.get():
                self.close_bh_var.set("Exit App")
                self.save_settings()
            dialog.destroy()
            self.quit()

        ctk.CTkButton(btn_frame, text="Minimize to Tray", command=minimize).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_frame, text="Exit", fg_color="#7a2d2d", hover_color="#5c1f1f",
                      command=exit_app).pack(side="left", fill="x", expand=True)

    def _do_minimize_to_tray(self):
        self.withdraw()
        image = self.create_image()
        menu = pystray.Menu(
            item('Show', self.show_window, default=True),
            item('Quit', self.quit_window)
        )
        self.tray_icon = pystray.Icon("DesktopLEDSync", image, "Desktop LED Sync", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def show_window(self, icon, item):
        self.tray_icon.stop()
        self.deiconify()

    def quit_window(self, icon, item):
        self.tray_icon.stop()
        self.quit()

if __name__ == "__main__":
    # --- Single Instance Guard ---
    # Create a named Windows mutex. If it already exists, another copy is running.
    MUTEX_NAME = "DesktopLEDSync_SingleInstanceMutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # Briefly show a Tk root just to display the messagebox, then exit
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Already Running",
            "Desktop LED Sync is already running!"
        )
        root.destroy()
        sys.exit(0)

    app = DesktopLEDSyncGUI()
    app.mainloop()

    # Release the mutex when the app closes cleanly
    ctypes.windll.kernel32.ReleaseMutex(mutex)
    ctypes.windll.kernel32.CloseHandle(mutex)
