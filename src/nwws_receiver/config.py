"""Configuration for NWWS-OI."""

from dataclasses import dataclass, field


class ConfigurationError(ValueError):
    """Raised when configuration validation fails."""


def _validate_email(email: str, field_name: str = "email") -> str:
    """Validate email field.

    Args:
        email: Email address to validate
        field_name: Name of the field for error messages

    Returns:
        Validated and stripped email address

    Raises:
        ConfigurationError: If email is empty or invalid

    """
    if not email or not email.strip():
        msg = f"{field_name.capitalize()} address must not be empty"
        raise ConfigurationError(msg)
    return email.strip()


def _validate_port(port: int, field_name: str = "port") -> int:
    """Validate port number.

    Args:
        port: Port number to validate
        field_name: Name of the field for error messages

    Returns:
        Validated port number

    Raises:
        ConfigurationError: If port is out of valid range

    """
    if not (1 <= port <= 65535):
        msg = f"{field_name.capitalize()} must be between 1 and 65535, got {port}"
        raise ConfigurationError(msg)
    return port


def _validate_history(history: int, field_name: str = "history") -> int:
    """Validate history value.

    Args:
        history: History value to validate
        field_name: Name of the field for error messages

    Returns:
        Validated history value

    Raises:
        ConfigurationError: If history is negative

    """
    if history < 0:
        msg = f"{field_name.capitalize()} must be non-negative, got {history}"
        raise ConfigurationError(msg)
    return history


@dataclass(frozen=True)
class EmwinConfig:
    """Configuration for EMWIN module.

    This configuration is loaded from environment variables with the EMWIN_ prefix.
    Environment variables are case-insensitive and whitespace is automatically stripped.

    Attributes:
        email: Email address for EMWIN logon (required).

    Environment Variables:
        EMWIN_EMAIL: Email address for authentication

    """

    email: str = field(default="")

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.email:
            validated_email = _validate_email(self.email, "email")
            object.__setattr__(self, "email", validated_email)
        else:
            msg = "Email address must not be empty"
            raise ConfigurationError(msg)


@dataclass(frozen=True)
class WxWireConfig:
    """Configuration for Weather Wire module.

    This configuration handles XMPP connection settings for the NWWS-OI service.
    Environment variables should use the NWWS_ prefix (e.g., NWWS_USERNAME, NWWS_SERVER).
    Environment variables are case-insensitive and whitespace is automatically stripped.

    Attributes:
        username: XMPP username for NWWS-OI authentication (required for production use).
        password: XMPP password for NWWS-OI authentication (required for production use).
        server: XMPP server hostname for NWWS-OI connection.
        port: XMPP server port number.
        history: Number of historical messages to retrieve upon connection.

    Environment Variables:
        NWWS_USERNAME: XMPP username
        NWWS_PASSWORD: XMPP password
        NWWS_SERVER: XMPP server hostname
        NWWS_PORT: XMPP server port
        NWWS_HISTORY: Number of historical messages

    """

    username: str = field(default="")
    password: str = field(default="")
    server: str = field(default="nwws-oi.weather.gov")
    port: int = field(default=5222)
    history: int = field(default=10)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.username:
            object.__setattr__(self, "username", self.username.strip())
        if self.password:
            object.__setattr__(self, "password", self.password.strip())

        server = self.server.strip() if self.server else ""
        if not server:
            server = "nwws-oi.weather.gov"
        object.__setattr__(self, "server", server)

        # Validate port and history
        validated_port = _validate_port(self.port, "port")
        object.__setattr__(self, "port", validated_port)

        validated_history = _validate_history(self.history, "history")
        object.__setattr__(self, "history", validated_history)
