"""XMPP client package for NWWS-OI."""

from .config import ConfigurationError, WxWireConfig
from .message import NoaaPortMessage
from .wx_wire import MessageHandler, WxWire

__version__ = "1.0.0"

__all__ = [
    "ConfigurationError",
    "MessageHandler",
    "NoaaPortMessage",
    "WxWire",
    "WxWireConfig",
    "__version__",
]
