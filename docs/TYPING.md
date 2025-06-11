# Typing Support

The `nwws-oi-receiver` library is fully typed and provides comprehensive type information for all public APIs. This document explains how to use the library with type checkers and IDEs.

## Type Checker Support

This library includes a `py.typed` marker file and is configured with the `Typing :: Typed` classifier, making it compatible with:

- **basedpyright** / **Pyright** (recommended)
- **mypy**
- **PyCharm**
- **VS Code** with Python extension
- Other PEP 561 compliant type checkers

## Installation

```bash
pip install nwws-oi-receiver
```

The typing information is automatically available after installation - no additional steps required.

## Basic Usage with Type Hints

```python
from wx_wire import (
    WxWire,
    WxWireConfig,
    NoaaPortMessage,
)

# Type checker will validate this configuration
config: WxWireConfig = WxWireConfig(
    email="user@example.com",
    server_host="nwws-oi.weather.gov",
    server_port=5223
)

# Async callback with proper typing
async def handle_message(message: NoaaPortMessage) -> None:
    product_id: str = message.product_id
    content: str = message.content
    print(f"Received {product_id}: {len(content)} characters")

# Client with type safety
client: WxWire = WxWire(config)
client.subscribe(handle_message)  # Type checker validates callback signature
```

## Advanced Type Usage

### Message Models

```python
from wx_wire import NoaaPortMessage, WxWireConfig

# Message handling with full type safety
def process_message(message: NoaaPortMessage) -> None:
    product_id: str = message.product_id
    message_id: str = message.message_id
    content: str = message.content
    timestamp: datetime = message.timestamp

# Configuration management
def handle_config(config: WxWireConfig) -> None:
    email: str = config.email
    host: str = config.server_host
    port: int = config.server_port
```

### Custom Handlers

```python
from typing import Protocol
from wx_wire import NoaaPortMessage

class MessageHandler(Protocol):
    """Protocol for message handling callbacks."""
    
    async def __call__(self, message: NoaaPortMessage) -> None:
        """Handle a weather message."""
        ...

# Type-safe custom handler
class CustomMessageHandler:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
    
    async def __call__(self, message: NoaaPortMessage) -> None:
        # Implementation with full type safety
        path = Path(self.output_dir) / f"{message.product_id}_{message.message_id}.txt"
        path.write_text(message.content)

# Usage
handler: MessageHandler = CustomMessageHandler("./weather_data")
client.subscribe(handler)  # Type checker validates protocol compliance
```

## Type Checker Configuration

### basedpyright/Pyright

Add to your `pyrightconfig.json` or `pyproject.toml`:

```json
{
    "typeCheckingMode": "strict",
    "reportMissingTypeStubs": true,
    "reportUnknownVariableType": true
}
```

Or in `pyproject.toml`:

```toml
[tool.basedpyright]
typeCheckingMode = "strict"
reportMissingTypeStubs = true
reportUnknownVariableType = true
```

### mypy

Add to your `mypy.ini` or `pyproject.toml`:

```ini
[mypy]
strict = true
warn_return_any = true
warn_unused_configs = true
```

Or in `pyproject.toml`:

```toml
[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true
```

## Common Type Patterns

### Error Handling

```python
from typing import Union
import asyncio

async def safe_message_handler(message: NoaaPortMessage) -> None:
    try:
        # Process message with type safety
        content: str = message.content
        product_id: str = message.product_id
        
        # Your processing logic here
        
    except Exception as e:
        print(f"Error processing {message.product_id}: {e}")

# Exception handling in async context
async def robust_client() -> None:
    config = WxWireConfig(email="test@example.com")
    client = WxWire(config)
    
    try:
        await client.connect()
        await client.join_room()
        # Keep running
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await client.disconnect()
```

### Generic Callbacks

```python
from typing import Callable, Awaitable

# Type alias for message callbacks
MessageCallback = Callable[[NoaaPortMessage], Awaitable[None]]

def create_filtered_handler(pattern: str) -> MessageCallback:
    """Create a type-safe filtered message handler."""
    import re
    regex = re.compile(pattern)
    
    async def handler(message: NoaaPortMessage) -> None:
        if regex.match(message.product_id):
            print(f"Matched: {message.product_id}")
    
    return handler

# Usage with full type safety
weather_handler: MessageCallback = create_filtered_handler(r"^(WAR|WRN|WAT).*")
client.subscribe(weather_handler)
```

## IDE Integration

### VS Code

1. Install the Python extension
2. Enable type checking in settings:
   ```json
   {
       "python.analysis.typeCheckingMode": "strict",
       "python.analysis.autoImportCompletions": true
   }
   ```

### PyCharm

Type hints are automatically recognized. Enable stricter checking in:
- File → Settings → Editor → Inspections → Python
- Enable "Type checker compatibility" inspections

## Troubleshooting

### Missing Type Information

If your type checker reports missing type information:

1. **Verify installation**: Ensure `byte-blaster` is installed in the same environment as your type checker
2. **Check py.typed**: The package should include a `py.typed` file
3. **Update tools**: Ensure your type checker supports PEP 561

### Import Errors

```python
# ✅ Correct imports
from wx_wire import WxWire, WxWireConfig
from wx_wire import NoaaPortMessage

# ❌ Avoid internal imports
# from wx_wire._internal import ...  # May not be typed
```

### Type Stub Conflicts

If you have custom type stubs that conflict:

```bash
# Remove conflicting stubs
rm -rf typings/wx_wire*
```

## Version Compatibility

- **Python**: 3.12+
- **Type Checkers**: Any PEP 561 compliant checker
- **Typing Extensions**: No additional dependencies required

## Contributing Type Improvements

Found a typing issue? Please report it on our [GitHub Issues](https://github.com/your-username/nwws-oi-receiver/issues) with:

1. Your type checker and version
2. Code example that fails
3. Expected vs actual behavior

---

For more examples, see the [examples directory](../examples/) which includes fully typed usage patterns.