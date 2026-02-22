class LightProvider:
    """Base class that all specific LED light providers must inherit from."""
    
    def __init__(self, config):
        self.config = config
        self.ip_address = config.get("ip_address")
        self.credentials = config.get("credentials", {})
        self.settings = config.get("settings", {})
        
        if not self.ip_address or self.ip_address == "YOUR_LED_STRIP_IP":
            raise ValueError("Invalid IP address in config.json")

    async def connect(self):
        """Handle any necessary local authentication or handshakes (e.g., Tapo login)."""
        pass

    async def set_color(self, rgb_tuple):
        """
        Send the command to change the light color.
        :param rgb_tuple: A tuple of (Red, Green, Blue) from 0-255.
        """
        raise NotImplementedError("Each provider must implement the set_color method.")
