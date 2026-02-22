import requests
import asyncio
from . import LightProvider

class WLEDProvider(LightProvider):
    """
    Provider for WLED smart lights.
    WLED uses a completely open, unauthenticated REST API.
    """
    def __init__(self, config):
        super().__init__(config)
        self.api_url = f"http://{self.ip_address}/json/state"
        self.info_url = f"http://{self.ip_address}/json/info"

    async def connect(self):
        """Verify the WLED device is reachable by fetching its info endpoint."""
        try:
            response = await asyncio.to_thread(requests.get, self.info_url, timeout=3)
            if response.status_code == 200:
                info = response.json()
                name = info.get("name", "WLED Device")
                version = info.get("ver", "unknown")
                self._log("ok", f"Connected to WLED: '{name}' (v{version}) at {self.ip_address}")
            else:
                raise ConnectionError(f"Unexpected status code: {response.status_code}")
        except Exception as e:
            raise ConnectionError(f"Could not reach WLED device at {self.ip_address}: {e}")

    async def set_color(self, rgb_tuple):
        """Send the JSON payload to change the light color."""
        r, g, b = rgb_tuple

        payload = {
            "on": True,
            "bri": 255,  # Full brightness
            # TODO: add "transition": <deciseconds> here for smooth cross-fades
            # e.g. "transition": 15 = 1.5 second fade (WLED uses deciseconds)
            "seg": [
                {
                    "id": 0,
                    "col": [[r, g, b]]
                }
            ]
        }

        try:
            response = await asyncio.to_thread(
                requests.post, self.api_url, json=payload, timeout=2
            )
            if response.status_code != 200:
                self._log("error", f"[WLED] Error setting color (HTTP {response.status_code})")
        except Exception as e:
            self._log("error", f"[WLED] Failed to send color: {e}")

    def _log(self, level, message):
        """Forward log messages to the GUI queue if available, else print."""
        import core
        print(message)
        if core.log_queue is not None:
            core.log_queue.put((level, message))
