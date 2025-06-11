# Async Iterator Usage Guide

This guide demonstrates how to use the async iterator interface with WxWire (NWWS-OI Receiver), showcasing modern Python 3.12+ patterns for event-driven programming.

## Overview

WxWire supports both callback-based and async iterator patterns for processing weather message streams:

- **Callback Pattern**: Traditional event handlers (existing functionality)
- **Async Iterator Pattern**: Modern structured concurrency with `async with` and `async for`

## Basic Usage

### 1. Weather Message Stream Processing

```python
import asyncio
from pathlib import Path
from wx_wire import WxWire, WxWireConfig

async def process_messages():
    config = WxWireConfig(
        email="your@email.com",
        server_host="nwws-oi.weather.gov",
        server_port=5223
    )
    client = WxWire(config)
    
    await client.connect()
    
    # Process weather messages using async iterator
    async for message in client:
        print(f"Received: {message.message_id}")
        print(f"Product: {message.product_id}")
        print(f"Content: {message.content[:100]}...")
        # Process message here
        await save_message(message)

async def save_message(message):
    output_dir = Path("weather_data")
    output_dir.mkdir(exist_ok=True)
    filename = f"{message.product_id}_{message.message_id}.txt"
    (output_dir / filename).write_text(message.content)
```

### 2. Subscribe/Unsubscribe Pattern

```python
async def process_with_subscriptions():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    # Define message handler
    async def handle_weather_alert(message):
        if "ALERT" in message.content:
            print(f"Weather Alert: {message.product_id}")
    
    # Subscribe to messages
    client.subscribe(handle_weather_alert)
    
    await client.connect()
    await client.join_room()
    
    # Keep running to receive messages
    await asyncio.sleep(3600)  # Run for 1 hour
```

## Advanced Patterns

### 1. Concurrent Processing with TaskGroup

```python
async def concurrent_processing():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    await client.connect()
    await client.join_room()
    
    # Run multiple processors concurrently
    async with asyncio.TaskGroup() as tg:
        tg.create_task(process_weather_alerts(client))
        tg.create_task(process_forecasts(client))
        tg.create_task(monitor_health(client))

async def process_weather_alerts(client):
    async for message in client:
        if message.product_id.startswith(('WAR', 'WRN', 'WAT')):
            await process_alert_content(message)

async def process_forecasts(client):
    async for message in client:
        if message.product_id.startswith(('ZFP', 'AFD')):
            await process_forecast_content(message)

async def monitor_health(client):
    while True:
        await asyncio.sleep(60)  # Check every minute
        if not client.is_connected:
            print("Connection lost, attempting reconnect...")
            await client.reconnect()
```

### 2. Filtering and Batching

```python
async def filtered_batch_processing():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    await client.connect()
    await client.join_room()
    
    batch = []
    async for message in client:
        # Filter for weather alerts
        if message.product_id.startswith(('WAR', 'WRN', 'WAT')):
            batch.append(message)
            
            # Process in batches of 5
            if len(batch) >= 5:
                await process_alert_batch(batch)
                batch.clear()

async def process_alert_batch(alert_messages):
    """Process high-priority alerts together."""
    print(f"Processing {len(alert_messages)} alerts")
    async with asyncio.TaskGroup() as tg:
        for alert in alert_messages:
            tg.create_task(send_alert_notification(alert))
```

### 3. Backpressure Handling

```python
async def backpressure_example():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    await client.connect()
    await client.join_room()
    
    # Process messages with controlled rate
    async for message in client:
        # Slow processing will naturally limit throughput
        await slow_message_processing(message)
        await asyncio.sleep(1.0)  # Simulate slow processing

async def slow_message_processing(message):
    """Simulate time-consuming message processing."""
    print(f"Processing {message.product_id}...")
    await asyncio.sleep(2.0)  # Simulate heavy processing
```

### 4. Error Handling and Recovery

```python
async def robust_processing():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    await client.connect()
    await client.join_room()
    
    try:
        async for message in client:
            try:
                await process_message_safely(message)
            except ProcessingError as e:
                logger.warning("Message processing failed: %s", e)
                await handle_processing_error(message, e)
            except Exception:
                logger.exception("Unexpected error processing message: %s", message.product_id)
    except asyncio.CancelledError:
        logger.info("Message processing cancelled")
        raise
    finally:
        await client.disconnect()
```

### 5. Priority Processing

```python
async def priority_processing():
    config = WxWireConfig(email="your@email.com")
    client = WxWire(config)
    
    await client.connect()
    await client.join_room()
    
    # Separate high and low priority queues
    high_priority_queue = asyncio.Queue(maxsize=50)
    low_priority_queue = asyncio.Queue(maxsize=200)
    
    async with asyncio.TaskGroup() as tg:
        # Classifier task
        tg.create_task(classify_messages(client, high_priority_queue, low_priority_queue))
        
        # Priority processors
        tg.create_task(process_high_priority(high_priority_queue))
        tg.create_task(process_low_priority(low_priority_queue))

async def classify_messages(client, high_queue, low_queue):
    async for message in client:
        if message.product_id.startswith(('WAR', 'WRN', 'WAT', 'TOR', 'SVR')):
            await high_queue.put(message)
        else:
            await low_queue.put(message)

async def process_high_priority(queue):
    while True:
        message = await queue.get()
        print(f"🚨 High priority: {message.product_id}")
        await urgent_message_processing(message)

async def process_low_priority(queue):
    while True:
        message = await queue.get()
        print(f"📄 Low priority: {message.product_id}")
        await standard_message_processing(message)
```

## Comparison: Callbacks vs Async Iterators

### Callback Pattern (Traditional)

```python
# Simple and familiar
client.subscribe(save_message_callback)
client.subscribe(validate_message_callback)
client.subscribe(process_message_callback)

await client.connect()
await client.join_room()
# Handlers are called automatically
```

**Pros:**
- Simple and straightforward
- Low overhead
- Familiar to most developers
- Good for simple event handling

**Cons:**
- No natural backpressure
- Harder to compose/chain operations
- No built-in flow control

### Async Iterator Pattern (Modern)

```python
# Structured and composable
async for message in client:
    await save_message(message)
    await validate_message(message)
    await process_message(message)
```

**Pros:**
- Natural backpressure handling
- Easy to compose with other async iterators
- Built-in cancellation support
- Structured concurrency friendly
- Can easily filter, map, reduce streams
- Clear lifecycle management

**Cons:**
- Slightly more complex
- Requires understanding of async context managers

## Best Practices

### 1. Use Appropriate Message Processing

```python
# For high-throughput scenarios
async for message in client:
    # Process immediately without queuing
    await process_message(message)

# For memory-constrained environments with batching
async def batched_processing():
    batch = []
    async for message in client:
        batch.append(message)
        if len(batch) >= 10:
            await process_batch(batch)
            batch.clear()
```

### 2. Handle Cancellation Gracefully

```python
async def graceful_processing():
    try:
        async for message in client:
            await process_message(message)
    except asyncio.CancelledError:
        logger.info("Processing cancelled gracefully")
        raise  # Re-raise to propagate cancellation
```

### 3. Use TaskGroups for Concurrency

```python
# Structured concurrency with proper error handling
async with asyncio.TaskGroup() as tg:
    tg.create_task(process_messages())
    tg.create_task(monitor_connection())
    tg.create_task(log_statistics())
```

### 4. Implement Proper Error Isolation

```python
async def isolated_processing():
    async for message in client:
        async with asyncio.TaskGroup() as tg:
            # Each message processed in isolation
            tg.create_task(save_message(message))
            tg.create_task(validate_message(message))
            # If one fails, others in this group are cancelled
```

## Migration Guide

If you're upgrading from callback-only usage:

### Before (Callback Only)
```python
async def save_message(message):
    # Save logic here
    pass

client.subscribe(save_message)
await client.connect()
await client.join_room()
```

### After (Both Options Available)
```python
# Option 1: Keep using callbacks (no changes needed)
client.subscribe(save_message)

# Option 2: Use async iterators for new code
async for message in client:
    await save_message(message)
```

Both patterns can be used simultaneously in the same application, allowing for gradual migration and choosing the best pattern for each use case.