import asyncio
import colorsys
from plugp100.common.credentials import AuthCredential
from plugp100.new.device_factory import connect, DeviceConnectConfiguration
from plugp100.new.components.light_component import LightComponent

from . import LightProvider

class TapoProvider(LightProvider):
    """
    Provider for TP-Link Tapo smart lights.
    Requires 'plugp100' library version 5+.
    """
    def __init__(self, config):
        super().__init__(config)
        self.username = config.get("credentials", {}).get("username")
        self.password = config.get("credentials", {}).get("password")
        
        if not self.username or not self.password:
            raise ValueError("Tapo provider requires 'username' and 'password' in config.json credentials.")
            
        self.device = None
        self.light_component = None

    def _log(self, level, message):
        """Forward log messages to GUI queue if available, else print."""
        import core
        print(message)
        if core.log_queue is not None:
            core.log_queue.put((level, message))

    async def connect(self):
        """Asynchronously authenticate and connect to the Tapo light."""
        self._log("info", f"[Tapo] Connecting to {self.ip_address}...")
        credentials = AuthCredential(self.username, self.password)
        dev_config = DeviceConnectConfiguration(self.ip_address, credentials=credentials)
        self.device = await connect(dev_config)
        
        # Some devices like the L920 might not be auto-detected by V5's factory,
        # so we inject the authenticated client directly into a new LightComponent.
        self.light_component = LightComponent(self.device.client)
        self._log("ok", f"[Tapo] Connected to device at {self.ip_address}")

    async def set_color(self, rgb_tuple):
        """Asynchronously send the color command."""
        if not self.light_component:
            self._log("error", "[Tapo] Cannot set color — light is not connected.")
            return

        r, g, b = rgb_tuple

        # Special case: (0, 0, 0) means "turn off"
        if r == 0 and g == 0 and b == 0:
            try:
                await self.light_component.turn_off()
                self._log("info", "[Tapo] Lights turned off (idle).")
            except Exception as e:
                self._log("error", f"[Tapo] Failed to turn off: {e}")
            return

        # Convert RGB to HSV. Tapo uses hue + saturation for color control.
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        hue = int(h * 360)
        saturation = int(s * 100)

        # Re-read config to honour the "Match album art brightness" toggle live
        import core
        live_config = core.load_config() if hasattr(core, 'load_config') else self.config
        match_brightness = live_config.get("settings", {}).get("match_brightness", False)
        if match_brightness:
            brightness = max(10, int(v * 100))  # Derived from album art value
        else:
            brightness = 100  # Always full brightness

        try:
            await self.light_component.turn_on()  # Wake up if previously turned off
            await self.light_component.set_hue_saturation(hue, saturation)
            await self.light_component.set_brightness(brightness)
            self._log("info", f"[Tapo] Set HSV({hue}°, {saturation}%, {brightness}%)")
        except Exception as e:
            self._log("error", f"[Tapo] Failed to set color: {e}")
