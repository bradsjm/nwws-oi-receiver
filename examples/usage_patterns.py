#!/usr/bin/env python3
"""Example demonstrating both async iterator and subscribe/unsubscribe patterns."""

import asyncio
import os
import signal
from contextlib import suppress

from nwws_receiver import NoaaPortMessage, WxWire, WxWireConfig


def message_logger(message: NoaaPortMessage) -> None:
    """Log incoming messages to demonstrate subscribe/unsubscribe pattern.

    This demonstrates the subscribe/unsubscribe pattern for event-driven processing.
    """
    print(f"[SUBSCRIBER] Received: {message.awipsid} - {message.subject}")


def priority_alert_handler(message: NoaaPortMessage) -> None:
    """Process only priority weather alerts with filtering logic.

    This shows how multiple subscribers can have different filtering logic.
    """
    if message.awipsid.startswith(("TOR", "SVR", "FFW", "EWW")):
        print(f"[PRIORITY] ⚠️  ALERT: {message.awipsid} - {message.subject}")


async def async_iterator_consumer(client: WxWire) -> None:
    """Consume messages via async iterator pattern concurrently with subscribers.

    This runs concurrently with the subscriber pattern, showing that
    both can operate simultaneously.
    """
    message_count = 0

    async for _message in client:
        message_count += 1
        if message_count % 10 == 0:  # Log every 10th message
            print(f"[ITERATOR] Processed {message_count} messages via async iterator")

        # Process message here...
        # For demo, we'll just count them


async def main() -> None:
    """Run comprehensive example demonstrating flexible consumption patterns."""
    # Configure the client (use environment variables for credentials)
    config = WxWireConfig(
        username=os.getenv("NWWS_USERNAME", "your_username"),
        password=os.getenv("NWWS_PASSWORD", "your_password"),
        server="nwws-oi.weather.gov",
        port=5222,
        history=5,  # Get last 5 messages when joining
    )

    # Create the client
    client = WxWire(config)

    # Method 1: Subscribe pattern for event-driven processing
    print("Setting up subscribers...")
    client.subscribe(message_logger)
    client.subscribe(priority_alert_handler)
    print(f"Active subscribers: {client.subscriber_count}")

    # Method 2: Start async iterator task for streaming processing
    print("Starting async iterator task...")
    iterator_task = asyncio.create_task(
        async_iterator_consumer(client), name="async_iterator_consumer"
    )

    # Set up graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler() -> None:
        print("\nReceived shutdown signal...")
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda _s, _f: signal_handler())

    try:
        print("Connecting to NWWS-OI...")
        success = await client.start()
        if not success:
            print("Failed to connect to NWWS-OI")
            return

        print("Connected! Processing messages...")
        print("Use Ctrl+C to gracefully shutdown")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except KeyboardInterrupt:
        print("\nShutdown requested...")
    finally:
        print("Shutting down...")

        # Cancel the async iterator task
        iterator_task.cancel()
        with suppress(asyncio.CancelledError):
            await iterator_task

        # Stop the client
        await client.stop("Example shutdown")
        print("Client stopped.")

        # Optionally unsubscribe handlers (not necessary during shutdown)
        client.unsubscribe(message_logger)
        client.unsubscribe(priority_alert_handler)
        print(f"Remaining subscribers: {client.subscriber_count}")


async def simple_subscriber_example() -> None:
    """Run simple example using only the subscriber pattern."""
    config = WxWireConfig(
        username=os.getenv("NWWS_USERNAME", "your_username"),
        password=os.getenv("NWWS_PASSWORD", "your_password"),
    )

    client = WxWire(config)

    # Define a simple handler
    def handle_message(message: NoaaPortMessage) -> None:
        print(f"Got message: {message.awipsid}")

    # Subscribe and run
    client.subscribe(handle_message)

    try:
        await client.start()
        await asyncio.sleep(30)  # Run for 30 seconds
    finally:
        await client.stop()


async def simple_iterator_example() -> None:
    """Run simple example using only the async iterator pattern."""
    config = WxWireConfig(
        username=os.getenv("NWWS_USERNAME", "your_username"),
        password=os.getenv("NWWS_PASSWORD", "your_password"),
    )

    client = WxWire(config)

    try:
        await client.start()

        # Process first 10 messages then exit
        count = 0
        async for message in client:
            print(f"Message {count + 1}: {message.awipsid}")
            count += 1
            if count >= 10:
                break

    finally:
        await client.stop()


def run_examples() -> None:
    """Run examples based on command line arguments or default to main."""
    import sys

    if len(sys.argv) > 1:
        example_type = sys.argv[1].lower()
        if example_type == "subscriber":
            print("Running subscriber-only example...")
            asyncio.run(simple_subscriber_example())
        elif example_type == "iterator":
            print("Running iterator-only example...")
            asyncio.run(simple_iterator_example())
        elif example_type == "main":
            print("Running comprehensive example...")
            asyncio.run(main())
        else:
            print("Usage: python usage_patterns.py [main|subscriber|iterator]")
            print("  main       - Run comprehensive example (default)")
            print("  subscriber - Run subscriber-only example")
            print("  iterator   - Run iterator-only example")
    else:
        # Run the comprehensive example by default
        print(
            "Running comprehensive example (use 'subscriber' or 'iterator' args for alternatives)"
        )
        asyncio.run(main())


if __name__ == "__main__":
    run_examples()
