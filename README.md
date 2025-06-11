# NWWS-OI Receiver

A robust Python implementation of the **NWWS-OI (NOAAPort Weather Wire Service - Open Interface)** XMPP protocol for receiving real-time weather data from the National Weather Service. This client connects to the NWWS-OI XMPP server and joins Multi-User Chat (MUC) rooms to receive weather messages, alerts, and forecasts.

## Requirements

- **Python 3.12+** (Python 3.13 recommended for best performance)
- **slixmpp** - Modern XMPP library for Python

## Overview

The NWWS-OI protocol uses XMPP (Extensible Messaging and Presence Protocol) to deliver weather data, forecasts, warnings, and other meteorological information in real-time. This Python client provides a robust, asynchronous implementation with automatic reconnection, comprehensive error handling, and flexible message consumption patterns.

## Features

- **Complete XMPP Protocol Implementation**: Full support for NWWS-OI XMPP protocol
- **Dual Consumption Patterns**: Both async iterator and subscribe/unsubscribe patterns
- **Multi-User Chat (MUC) Support**: Automatic room joining and presence management
- **Async Iterator Support**: Modern async/await patterns with `async for` message streaming
- **Event-Driven Architecture**: Subscribe to message events with custom handlers
- **Automatic Reconnection**: Intelligent reconnection with exponential backoff
- **Health Monitoring**: Idle timeout detection and connection monitoring
- **Message Parsing**: Structured NOAAPort message parsing with metadata extraction
- **Configuration Management**: Comprehensive configuration with validation
- **Production Ready**: Comprehensive logging, error handling, and type hints
- **Graceful Shutdown**: Proper cleanup and resource management

## Installation

### From PyPI (Recommended)

```bash
# Install latest version
pip install nwws-oi-receiver

# Install with optional dependencies
pip install nwws-oi-receiver[dev,test]
```

### Using Modern Package Managers

#### Using UV (Fastest)
```bash
# Install in current environment
uv add nwws-oi-receiver

# Create new project with nwws-oi-receiver
uv init my-weather-app
cd my-weather-app
uv add nwws-oi-receiver
```

#### Using Poetry
```bash
# Add to existing project
poetry add nwws-oi-receiver
```

#### Using PDM
```bash
# Add to project
pdm add nwws-oi-receiver
```

### From Source (Development)

```bash
# Clone the repository
git clone https://github.com/bradsjm/nwws-oi-receiver.git
cd nwws-oi-receiver

# Using UV (recommended for development)
uv sync --group dev --group test
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Using pip
pip install -e ".[dev,test]"
```

### Verify Installation

```bash
# Test basic import
python -c "from nwws_receiver import WxWire; print('✅ Installation successful')"

# Run examples
python examples/usage_patterns.py
```

## Quick Start

### Simple Subscriber Pattern

```python
import asyncio
import os
from nwws_receiver import WxWire, WxWireConfig, NoaaPortMessage

def handle_message(message: NoaaPortMessage) -> None:
    """Handle incoming weather messages."""
    print(f"Received: {message.awipsid} - {message.subject}")

    # Process message based on type
    if message.awipsid.startswith("TOR"):
        print(f"🌪️ TORNADO WARNING: {message.subject}")
    elif message.awipsid.startswith("SVR"):
        print(f"⛈️ SEVERE WEATHER: {message.subject}")

async def main():
    # Configure the client
    config = WxWireConfig(
        username=os.getenv("NWWS_USERNAME", "your_username"),
        password=os.getenv("NWWS_PASSWORD", "your_password"),
        server="nwws-oi.weather.gov",
        port=5222
    )

    # Create and configure client
    client = WxWire(config)
    client.subscribe(handle_message)

    try:
        # Connect and start receiving messages
        success = await client.start()
        if not success:
            print("Failed to connect to NWWS-OI")
            return

        print("Connected! Receiving weather data...")
        print("Press Ctrl+C to stop")

        # Keep running until interrupted
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("\\nShutting down...")
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

### Async Iterator Pattern

```python
import asyncio
import os
from nwws_receiver import WxWire, WxWireConfig

async def main():
    config = WxWireConfig(
        username=os.getenv("NWWS_USERNAME", "your_username"),
        password=os.getenv("NWWS_PASSWORD", "your_password")
    )

    client = WxWire(config)

    try:
        await client.start()

        # Process messages using async iterator
        async for message in client:
            print(f"Processing: {message.awipsid} - {message.subject}")

            # Custom processing logic here
            if "URGENT" in message.subject.upper():
                print(f"🚨 URGENT: {message.content}")

    except KeyboardInterrupt:
        print("\\nStopping...")
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

## Advanced Usage

### Dual Pattern Example

You can use both subscriber and async iterator patterns simultaneously:

```python
import asyncio
from nwws_receiver import WxWire, WxWireConfig, NoaaPortMessage

def priority_handler(message: NoaaPortMessage) -> None:
    """Handle priority alerts immediately."""
    if message.awipsid.startswith(("TOR", "FFW", "EWW")):
        print(f"🚨 PRIORITY ALERT: {message.awipsid}")

async def background_processor(client: WxWire) -> None:
    """Background task processing all messages."""
    async for message in client:
        # Log all messages to database, file, etc.
        print(f"[LOG] {message.awipsid}: {message.subject}")

async def main():
    config = WxWireConfig(
        username="your_username",
        password="your_password"
    )

    client = WxWire(config)

    # Set up priority subscriber
    client.subscribe(priority_handler)

    # Start background processor task
    processor_task = asyncio.create_task(background_processor(client))

    try:
        await client.start()
        await asyncio.Event().wait()  # Run forever
    except KeyboardInterrupt:
        processor_task.cancel()
    finally:
        await client.stop()

asyncio.run(main())
```

### Configuration Options

```python
from nwws_receiver import WxWireConfig

config = WxWireConfig(
    username="your_username",              # NWWS-OI username
    password="your_password",              # NWWS-OI password
    server="nwws-oi.weather.gov",         # XMPP server (default)
    port=5222,                            # XMPP port (default)
    room="nwws-oi@conference.weather.gov", # MUC room (default)
    nickname="your_nickname",             # MUC nickname (optional)
    history=0,                           # Message history to request (default: 0)
    idle_timeout=300,                    # Idle timeout in seconds (default: 300)
    max_reconnect_attempts=10,           # Max reconnection attempts (default: 10)
    reconnect_delay=5.0,                 # Initial reconnect delay (default: 5.0)
    use_tls=True,                       # Use TLS encryption (default: True)
    validate_certificates=True          # Validate SSL certificates (default: True)
)
```

## Message Structure

The `NoaaPortMessage` class provides structured access to weather data:

```python
from nwws_receiver import NoaaPortMessage

def process_message(message: NoaaPortMessage) -> None:
    print(f"AWIPS ID: {message.awipsid}")           # Product identifier
    print(f"Subject: {message.subject}")            # Message subject
    print(f"Content: {message.content}")            # Message body
    print(f"Timestamp: {message.timestamp}")        # Message timestamp
    print(f"Source: {message.source}")              # Originating office
    print(f"Raw XML: {message.raw_xml}")            # Original XML
```

## Authentication

To use NWWS-OI, you need to register for an account:

1. Visit the [NWWS-OI Registration Page](https://nwws-oi.weather.gov/)
2. Complete the registration process
3. Wait for account approval (typically 1-2 business days)
4. Use your approved credentials in the configuration

## Error Handling

The client includes comprehensive error handling:

```python
import logging
from nwws_receiver import WxWire, WxWireConfig

# Enable detailed logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def robust_client():
    config = WxWireConfig(
        username="your_username",
        password="your_password",
        max_reconnect_attempts=5,
        reconnect_delay=10.0
    )

    client = WxWire(config)

    try:
        success = await client.start()
        if not success:
            logger.error("Failed to connect after all attempts")
            return

        # Client will automatically reconnect on network issues
        async for message in client:
            try:
                # Process message
                process_weather_data(message)
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except Exception as e:
        logger.error(f"Client error: {e}")
    finally:
        await client.stop()
```

## Examples

The `examples/` directory contains comprehensive examples:

- `usage_patterns.py` - Complete example showing both consumption patterns
- Run examples with: `python examples/usage_patterns.py`

## API Reference

### WxWire Class

The main client class for connecting to NWWS-OI.

#### Methods

- `subscribe(handler)` - Subscribe to message events
- `unsubscribe(handler)` - Remove message subscription
- `start()` - Connect and start receiving messages (async)
- `stop(reason=None)` - Disconnect and cleanup (async)
- `__aiter__()` - Async iterator interface

#### Properties

- `subscriber_count` - Number of active subscribers
- `is_connected` - Connection status
- `config` - Current configuration

### WxWireConfig Class

Configuration management with validation.

#### Parameters

- `username` (str) - NWWS-OI username
- `password` (str) - NWWS-OI password
- `server` (str) - XMPP server hostname
- `port` (int) - XMPP server port
- `room` (str) - MUC room to join
- `nickname` (str) - MUC nickname
- `history` (int) - Message history count
- `idle_timeout` (float) - Connection idle timeout
- `max_reconnect_attempts` (int) - Maximum reconnection attempts
- `reconnect_delay` (float) - Initial reconnect delay
- `use_tls` (bool) - Enable TLS encryption
- `validate_certificates` (bool) - Validate SSL certificates

### NoaaPortMessage Class

Structured weather message representation.

#### Attributes

- `awipsid` (str) - AWIPS product identifier
- `subject` (str) - Message subject line
- `content` (str) - Message content/body
- `timestamp` (datetime) - Message timestamp
- `source` (str) - Originating weather office
- `raw_xml` (str) - Original XML message

## Protocol Details

### XMPP Connection Flow

1. **TLS Connection**: Establish secure connection to XMPP server
2. **Authentication**: SASL authentication with username/password
3. **Resource Binding**: Bind to XMPP resource
4. **MUC Join**: Join the NWWS-OI multi-user chat room
5. **Message Reception**: Receive and parse weather messages
6. **Presence Management**: Maintain presence and handle disconnections

### Message Format

NWWS-OI messages are delivered as XMPP messages containing structured weather data in XML format. The client automatically parses these messages into `NoaaPortMessage` objects.

### Reconnection Logic

The client implements exponential backoff reconnection:
- Initial delay: 5 seconds (configurable)
- Maximum attempts: 10 (configurable)
- Backoff multiplier: 2.0
- Maximum delay: 300 seconds

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=nwws_receiver

# Run specific test categories
pytest -m unit
pytest -m integration
```

## Development

### Code Quality

```bash
# Format code
ruff format .

# Check code quality
ruff check --fix .

# Type checking
basedpyright
```

### Project Structure

```
src/nwws_receiver/
├── __init__.py          # Package exports
├── config.py            # Configuration management
├── message.py           # Message parsing
└── wx_wire.py           # Main XMPP client
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass (`pytest`)
6. Run code quality checks (`ruff check`, `basedpyright`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

- [NWWS-OI Official Documentation](https://nwws-oi.weather.gov/)
- [XMPP Protocol Specification](https://xmpp.org/rfcs/)
- [NOAAPort Data Format](https://www.weather.gov/tg/head)
- [AWIPS Product Identifiers](https://www.weather.gov/tg/awips)

## Support

For questions, issues, or contributions:

- Create an [issue on GitHub](https://github.com/bradsjm/nwws-oi-receiver/issues)
- Check the [examples](examples/) for usage patterns
- Review the comprehensive logging output for debugging

## Acknowledgments

### AI Assistance

This project has been developed with assistance from Large Language Models (LLMs), and we acknowledge their significant contributions to both the codebase and documentation:

- **Anthropic Claude** - Contributed to code architecture, implementation patterns, documentation structure, async/await patterns, error handling strategies, and comprehensive testing approaches
- **OpenAI GPT** - Assisted with protocol implementation details, API design decisions, code optimization suggestions, and example development
- **Google Gemini** - Provided insights on Python best practices, type annotation improvements, and packaging standards compliance

The LLMs have been instrumental in:
- **Code Quality**: Implementing modern Python 3.12+ features, type hints, and async patterns
- **Documentation**: Creating comprehensive README, API documentation, and example code
- **Architecture**: Designing modular, testable, and maintainable code structure
- **Standards Compliance**: Ensuring adherence to PEP standards and modern packaging practices
- **Error Handling**: Implementing robust error recovery and logging strategies

While AI has significantly accelerated development and improved code quality, all code has been reviewed, tested, and validated by human developers. The final implementation decisions, architecture choices, and quality standards remain under human oversight.

### Human Contributors

We also acknowledge the human developers, domain experts, and community members who have contributed to the project through code review, testing, feedback, and domain expertise in weather data protocols.

---

**Note**: You need valid NWWS-OI credentials to use this client. Register at [https://nwws-oi.weather.gov/](https://nwws-oi.weather.gov/) to obtain access.
