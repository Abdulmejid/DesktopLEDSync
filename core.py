import asyncio
import json
import os
import sys
from io import BytesIO

# Module-level variables injected by gui.py at runtime
log_queue = None
stop_event = None

def log(level, message):
    """Post a log message to the GUI queue, or fall back to print."""
    print(message)
    if log_queue is not None:
        log_queue.put((level, message))

from PIL import Image
from colorthief import ColorThief

# Light Providers
from providers.tapo import TapoProvider
from providers.wled import WLEDProvider

# Windows Runtime APIs
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
)
from winsdk.windows.storage.streams import DataReader, IRandomAccessStreamReference

# Configuration Setup
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(application_path, "config.json")

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Could not find {CONFIG_FILE}. Please configure your smart lights first.")
        sys.exit(1)
    
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

# --- Media Extraction Logic ---
async def get_media_session():
    """Gets the active Windows Media session (Spotify, Tidal, Web, etc)"""
    session_manager = await MediaManager.request_async()
    return session_manager.get_current_session()

async def get_thumbnail_stream(session):
    """Asks Windows for the album art reference of the current media"""
    media_properties = await session.try_get_media_properties_async()
    if media_properties and media_properties.thumbnail:
        return media_properties.thumbnail
    return None

async def read_stream_into_bytes(thumbnail_ref: IRandomAccessStreamReference) -> bytes:
    """Reads the Windows Runtime stream into a standard Python byte array"""
    try:
        # Open the stream
        stream = await thumbnail_ref.open_read_async()
        
        # Read the stream using a DataReader
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(stream.size)
        
        # The Windows Runtime buffer requires a specific read pattern in python
        # We need to extract the bytes manually into a standard python format
        buffer = bytearray(stream.size)
        reader.read_bytes(buffer)
        return bytes(buffer)
    except Exception as e:
        print(f"Error reading media stream: {e}")
        return None

def get_dominant_color(image_bytes):
    """Uses colorthief to find the most prominent vibrant color"""
    if not image_bytes:
        return None
        
    try:
        image_stream = BytesIO(image_bytes)
        color_thief = ColorThief(image_stream)
        
        # Pull 5 dominant colors and choose the first vibrant one
        palette = color_thief.get_palette(color_count=5)
        for color in palette:
            r, g, b = color
            # Simple saturation calculation as a vibrancy heuristic
            saturation = max(r, g, b) - min(r, g, b)
            if saturation > 50:
                return color
                
        # Fallback to absolute dominant if no vibrant colors are found
        return color_thief.get_color(quality=1)
    except Exception as e:
        print(f"Error extracting color: {e}")
        return None

# --- Provider Factory ---
def initialize_provider(config):
    provider_name = config.get("provider", "").lower()
    
    if provider_name == "tapo":
        return TapoProvider(config)
    elif provider_name == "wled":
        return WLEDProvider(config)
    else:
        log("error", f"Unknown provider '{provider_name}' in config.json")
        sys.exit(1)

# --- Main Event Loop ---
async def main():
    log("info", "Desktop LED Sync - Initializing...")
    config = load_config()
    log("info", f"Provider: {config.get('provider')} @ {config.get('ip_address')}")
    
    # Initialize the specific brand of lights the user has
    provider = initialize_provider(config)
    try:
        await provider.connect()
        log("ok", f"Connected to {config.get('provider')} at {config.get('ip_address')}")
    except Exception as e:
        log("error", f"Failed to connect: {e}")
        return
    
    last_known_title = None
    last_applied_idle_key = None  # Tracks (behavior, color) that was last sent to device
    last_known_color = None       # Tracks the RGB value of the current song
    last_match_brightness = config.get("settings", {}).get("match_brightness", False)
    
    poll_interval = config.get("settings", {}).get("poll_interval_seconds", 1.5)

    log("info", "Listening for media changes on Windows...")
    
    while stop_event is None or not stop_event.is_set():
        try:
            session = await get_media_session()
            if session:
                playback_info = session.get_playback_info()
                
                # We only care when music is actively playing
                if playback_info.playback_status == PlaybackStatus.PLAYING:
                    media_props = await session.try_get_media_properties_async()
                    current_title = media_props.title
                    
                    # Reset idle tracker whenever music is playing
                    last_applied_idle_key = None

                    # Check if 'Match Brightness' was toggled live in the GUI
                    live_config = load_config()
                    current_match_brightness = live_config.get("settings", {}).get("match_brightness", False)

                    # Did the song change or did the brightness setting change?
                    if current_title != last_known_title or current_match_brightness != last_match_brightness:
                        if current_title != last_known_title:
                            log("ok", f"Now Playing: {current_title} — {media_props.artist}")
                            last_known_title = current_title

                        last_match_brightness = current_match_brightness
                        
                        # Grab the album art
                        thumb_ref = await get_thumbnail_stream(session)
                        if thumb_ref:
                            image_bytes = await read_stream_into_bytes(thumb_ref)
                            color = get_dominant_color(image_bytes)
                            
                            if color:
                                last_known_color = color
                                log("ok", f"Color set: RGB{color}" + (" (Match Brightness changed)" if current_title == last_known_title else ""))
                                asyncio.create_task(provider.set_color(color))
                            else:
                                log("error", "Could not extract color from album art.")
                        else:
                            log("info", "No album art for this track.")
                            
                elif playback_info.playback_status in [PlaybackStatus.PAUSED, PlaybackStatus.STOPPED]:
                    # Re-read config on every idle tick so GUI changes are picked up live
                    live_config = load_config()
                    behavior = live_config.get("settings", {}).get("idle_behavior", "Do Nothing")
                    
                    # Backward compatibility mapping
                    val_map = {"default_color": "Default Color", "turn_off": "Turn Off", "do_nothing": "Do Nothing"}
                    behavior = val_map.get(behavior, behavior)
                    
                    idle_color = tuple(live_config.get("settings", {}).get("idle_color", [255, 200, 100]))

                    # Build a key representing the current desired idle state
                    current_idle_key = (behavior, idle_color)

                    # Only send a command when the settings have actually changed
                    if current_idle_key != last_applied_idle_key:
                        last_known_title = "IDLE_STATE"
                        last_applied_idle_key = current_idle_key
                        log("info", "Idle state — applying idle settings.")

                        if behavior == "Turn Off":
                            log("info", "Idle: Turning lights off.")
                            asyncio.create_task(provider.set_color((0, 0, 0)))
                        elif behavior == "Default Color":
                            log("info", f"Idle: Default color RGB{idle_color}")
                            asyncio.create_task(provider.set_color(idle_color))
                        else:
                            log("info", "Idle: Keeping last color.")
                            
        except Exception as e:
            log("error", f"Media loop error: {e}")
            
        await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    # Workaround for ProactorEventLoop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
