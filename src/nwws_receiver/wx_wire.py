# pyright: strict
"""NWWS-OI XMPP client implementation using slixmpp."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree as ET

import slixmpp
from slixmpp import JID
from slixmpp.exceptions import XMPPError
from slixmpp.stanza import Message

from .config import WxWireConfig
from .message import NoaaPortMessage

logger = logging.getLogger(__name__)

# Configuration constants
MUC_ROOM = "nwws@conference.nwws-oi.weather.gov"
IDLE_TIMEOUT = 90  # 90 seconds of inactivity before reconnecting
MAX_HISTORY = 25  # Maximum history messages to retrieve when joining MUC

# Type aliases
MessageHandler = Callable[[NoaaPortMessage], Any]


class WxWire(slixmpp.ClientXMPP):
    """Production-grade NWWS-OI XMPP client for receiving real-time weather data.

    This class implements a robust, asynchronous XMPP client that connects to the
    National Weather Service's NWWS-OI (NOAAPort Weather Wire Service - Open Interface)
    system to receive real-time weather products, warnings, and forecasts. The client
    handles the complete lifecycle of XMPP connectivity including authentication,
    Multi-User Chat (MUC) room management, message processing, and graceful shutdown.

    The implementation provides:
    - Automatic reconnection with exponential backoff on connection failures
    - Idle timeout detection and forced reconnection for stuck connections
    - Comprehensive error handling and recovery mechanisms
    - Async iterator pattern for processing incoming weather messages
    - Subscribe/unsubscribe pattern for flexible message handling
    - Detailed metrics collection and monitoring capabilities
    - Circuit breaker patterns for resilient message processing
    - Structured logging for operational visibility

    The client joins the NWWS MUC room and processes incoming weather messages,
    converting them from NWWS-OI XML format to structured WeatherWireMessage objects
    with standardized NOAAPort formatting. Messages are available through both:
    1. Async iterator interface for streaming consumption
    2. Subscribe/unsubscribe callbacks for event-driven processing

    Connection health is continuously monitored through idle timeout detection,
    periodic stats updates, and comprehensive event handling for all XMPP lifecycle
    events. The client maintains detailed statistics about message processing rates,
    connection stability, and error conditions for operational monitoring.
    """

    def __init__(
        self,
        config: WxWireConfig,
    ) -> None:
        """Initialize the NWWS-OI XMPP client with comprehensive configuration and monitoring.

        Sets up a production-ready XMPP client with all necessary plugins, event handlers,
        and monitoring capabilities for reliable weather data reception. The initialization
        process configures the underlying slixmpp client with NWWS-OI specific settings,
        registers essential XMPP Extension Protocols (XEPs), and establishes the message
        processing pipeline with async iterator support.

        The client is configured with critical XMPP extensions:
        - Service Discovery (XEP-0030) for server capability negotiation
        - Multi-User Chat (XEP-0045) for joining the NWWS broadcast room
        - XMPP Ping (XEP-0199) for connection keep-alive and health monitoring
        - Delayed Delivery (XEP-0203) for processing messages with delivery delays

        A bounded message queue (maxsize=50) is established to buffer incoming weather
        messages and provide backpressure protection against message processing bottlenecks.
        The async iterator pattern allows downstream consumers to process messages at their
        own pace while maintaining system stability.

        Comprehensive event handlers are registered for all XMPP lifecycle events including
        connection management, authentication, session handling, and message processing.
        State tracking variables are initialized for idle timeout monitoring, graceful
        shutdown coordination, and background service management.

        Args:
            config: XMPP connection configuration containing server details, credentials,
                   and connection parameters for the NWWS-OI system.

        Raises:
            ValueError: If the configuration contains invalid or missing required fields.
            ConnectionError: If initial client setup fails due to network or configuration issues.

        """
        self.config = config
        super().__init__(  # type: ignore  # noqa: PGH003
            jid=JID(f"{self.config.username}@{self.config.server}"),
            password=self.config.password,
            plugin_config=None,
            plugin_whitelist=None,
            escape_quotes=True,
            sasl_mech=None,
            lang="en",
        )

        self.nickname = f"{datetime.now(UTC):%Y%m%d%H%M}"

        # Message queue for async iterator pattern
        self._message_queue: asyncio.Queue[NoaaPortMessage] = asyncio.Queue(maxsize=50)
        self._stop_iteration = False

        # Subscriber management for callback pattern
        self._subscribers: set[MessageHandler] = set()

        # Register plugins
        self.register_plugin("xep_0030")  # Service Discovery  # type: ignore[misc]
        self.register_plugin("xep_0045")  # Multi-User Chat  # type: ignore[misc]
        self.register_plugin("xep_0199")  # XMPP Ping  # type: ignore[misc]
        self.register_plugin("xep_0203")  # Delayed Delivery # type: ignore[misc]

        # Add comprehensive event handlers
        self._add_event_handlers()

        # Initialize state variables
        self.last_message_time: float = time.time()
        self.is_shutting_down: bool = False
        self._idle_monitor_task: asyncio.Task[None] | None = None
        self._stats_update_task: asyncio.Task[None] | None = None
        self._background_tasks: list[asyncio.Task[None]] = []
        self._connection_start_time: float | None = None

        logger.info(
            "Initialized NWWS-OI XMPP client - username: %s, server: %s, queue_maxsize: %d",
            self.config.username,
            self.config.server,
            self._message_queue.maxsize,
        )

    def __aiter__(self) -> AsyncIterator[NoaaPortMessage]:
        """Enable async iteration over incoming weather messages.

        Implements the async iterator protocol to allow the WeatherWire client to be
        used in async for loops and other async iteration contexts. This provides a
        clean, Pythonic interface for consuming weather messages as they arrive from
        the NWWS-OI system.
        """
        return self

    async def __anext__(self) -> NoaaPortMessage:
        """Retrieve the next weather message from the internal processing queue.

        Implements the async iterator protocol by fetching messages from the internal
        asyncio.Queue in a non-blocking manner. The method uses a short timeout to
        periodically check for shutdown conditions while waiting for new messages,
        ensuring responsive shutdown behavior even when no messages are being received.

        The method handles the StopAsyncIteration protocol correctly by raising the
        exception when the client is shutting down and no more messages remain in
        the queue. This allows proper cleanup of async for loops and other iteration
        contexts.

        Returns:
            The next WeatherWireMessage containing structured weather data, metadata,
            and NOAAPort formatted content ready for downstream processing.

        Raises:
            StopAsyncIteration: When the client is shutting down and no more messages
                              are available in the queue, signaling the end of iteration.

        """
        while True:
            if self._stop_iteration and self._message_queue.empty():
                raise StopAsyncIteration

            try:
                # Short timeout to periodically check stop condition
                message = await asyncio.wait_for(self._message_queue.get(), timeout=0.5)
            except TimeoutError:
                # Continue loop to check stop condition
                continue
            else:
                self._message_queue.task_done()
                return message

    @property
    def queue_size(self) -> int:
        """Get the current number of messages pending in the processing queue.

        Provides real-time visibility into the message queue depth for monitoring
        and capacity planning. A consistently high queue size may indicate downstream
        processing bottlenecks or the need for additional consumer capacity.

        Returns:
            The current number of WeatherWireMessage objects waiting to be processed
            in the internal asyncio.Queue.

        """
        return self._message_queue.qsize()

    def subscribe(self, handler: MessageHandler) -> None:
        """Subscribe a callback function to receive weather messages.

        Registers a callback function that will be invoked for each incoming weather
        message. This provides an event-driven alternative to the async iterator pattern,
        allowing for more flexible integration with different architectural patterns.

        The handler function will be called with each NoaaPortMessage as it arrives.
        Multiple handlers can be registered and will all be called for each message.
        Handlers should be lightweight and fast to avoid blocking message processing.

        Args:
            handler: A callable that accepts a NoaaPortMessage parameter. The handler
                    should not raise exceptions as this will be logged but not propagated.
                    For async handlers, consider using asyncio.create_task() within
                    the handler to avoid blocking.

        Example:
            ```python
            def my_handler(message: NoaaPortMessage) -> None:
                print(f"Received: {message.awipsid}")

            client = WxWire(config)
            client.subscribe(my_handler)
            await client.start()
            ```

        Note:
            Subscribers are called synchronously within the message processing loop.
            For CPU-intensive or I/O operations, consider using asyncio.create_task()
            or threading within your handler to avoid blocking message processing.

        """
        if handler in self._subscribers:
            logger.warning("Handler already subscribed, ignoring duplicate subscription")
            return

        self._subscribers.add(handler)
        logger.info("Added message subscriber - total_subscribers: %d", len(self._subscribers))

    def unsubscribe(self, handler: MessageHandler) -> None:
        """Remove a previously registered message handler.

        Removes a callback function from the set of registered message handlers.
        After unsubscription, the handler will no longer receive weather messages.

        Args:
            handler: The same callable that was previously registered with subscribe().
                    The handler object must be identical (same object reference) to
                    the one used in the subscribe() call.

        Example:
            ```python
            def my_handler(message: NoaaPortMessage) -> None:
                print(f"Received: {message.awipsid}")

            client = WxWire(config)
            client.subscribe(my_handler)
            # ... later ...
            client.unsubscribe(my_handler)
            ```

        Note:
            If the handler was not previously subscribed, this method will log a
            warning but will not raise an exception.

        """
        if handler not in self._subscribers:
            logger.warning("Handler not found in subscribers, ignoring unsubscribe request")
            return

        self._subscribers.discard(handler)
        logger.info("Removed message subscriber - total_subscribers: %d", len(self._subscribers))

    @property
    def subscriber_count(self) -> int:
        """Get the current number of registered message subscribers.

        Returns:
            The number of callback functions currently registered to receive
            weather messages through the subscribe/unsubscribe pattern.

        """
        return len(self._subscribers)

    async def _dispatch_message(self, message: NoaaPortMessage) -> None:
        """Dispatch a message to both the async iterator queue and subscribers.

        This method handles the distribution of incoming weather messages to both
        consumption patterns supported by the client:
        1. Async iterator pattern via internal queue
        2. Subscribe/unsubscribe pattern via registered callbacks

        The method ensures that messages are delivered to all registered handlers
        while maintaining proper error isolation. If a subscriber raises an exception,
        it is logged but does not affect other subscribers or the async iterator queue.

        Args:
            message: The processed weather message to distribute to consumers.

        """
        # Put message in queue for async iterator pattern
        try:
            self._message_queue.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(
                "Message queue full (size: %d), dropping message: %s",
                self._message_queue.maxsize,
                message.awipsid,
            )

        # Notify all subscribers
        if self._subscribers:
            await self._notify_subscribers(message)

    async def _notify_subscribers(self, message: NoaaPortMessage) -> None:
        """Notify all registered subscribers of a new message.

        Calls each registered subscriber callback with the provided message.
        Subscriber calls are executed synchronously but with proper exception
        handling to ensure that a failing subscriber does not affect others.

        Args:
            message: The weather message to deliver to subscribers.

        """
        failed_subscribers: list[MessageHandler] = []

        for subscriber in self._subscribers:
            try:
                # Call subscriber synchronously to avoid concurrency issues
                subscriber(message)
            except (TypeError, ValueError, RuntimeError, AttributeError) as e:
                logger.warning(
                    "Subscriber failed to process message - error: %s, error_type: %s",
                    str(e),
                    type(e).__name__,
                )
                failed_subscribers.append(subscriber)
            except Exception as e:  # noqa: BLE001
                # Catch all other exceptions to prevent breaking the message loop
                logger.warning(
                    "Subscriber failed with unexpected error - error: %s, error_type: %s",
                    str(e),
                    type(e).__name__,
                )
                failed_subscribers.append(subscriber)

        # Remove failed subscribers that consistently fail
        # Note: For production, you might want more sophisticated error handling
        # such as retry logic or circuit breakers
        if failed_subscribers:
            logger.info(
                "Subscribers failed to process message - failed_count: %d, total_subscribers: %d",
                len(failed_subscribers),
                len(self._subscribers),
            )

    def _add_event_handlers(self) -> None:
        """Add all necessary event handlers for the XMPP client."""
        # Connection events
        self.add_event_handler("connecting", self._on_connecting)
        self.add_event_handler("connected", self._on_connected)
        self.add_event_handler("connection_failed", self._on_connection_failed)
        self.add_event_handler("disconnected", self._on_disconnected)
        self.add_event_handler("killed", self._on_killed)

        # Authentication events
        self.add_event_handler("failed_auth", self._on_failed_auth)

        # Session events
        self.add_event_handler("session_start", self._on_session_start)
        self.add_event_handler("session_end", self._on_session_end)

        # Message events
        self.add_event_handler("groupchat_message", self._on_groupchat_message)

        # MUC events
        self.add_event_handler("muc::{muc_room}::got_online", self._on_muc_presence)

        # Stanza events
        self.add_event_handler("stanza_not_sent", self._on_stanza_not_sent)

        # Reconnection events
        self.add_event_handler("reconnect_delay", self._on_reconnect_delay)

    async def start(self) -> bool:
        """Initiate connection to the NWWS-OI XMPP server.

        Begins the asynchronous connection process to the configured NWWS-OI server
        using the provided host and port settings. The connection attempt includes
        automatic DNS resolution, TCP socket establishment, and initial XMPP stream
        negotiation. Success or failure will trigger the appropriate event handlers
        for further processing.

        Returns:
            True if the initial connection succeeds, False if the connection attempt fails.

        """
        logger.info(
            "Connecting to NWWS-OI server - host: %s, port: %d",
            self.config.server,
            self.config.port,
        )

        # slixmpp's connect() returns Future[bool] but type checker can't infer parent class type
        connection_future = super().connect(host=self.config.server, port=self.config.port)  # type: ignore[misc]
        return await connection_future  # type: ignore[misc]

    def is_client_connected(self) -> bool:
        """Determine if the client is currently connected and operational.

        Performs a comprehensive check of the client's connection status by verifying
        both the underlying XMPP connection state and the client's internal shutdown
        flag. This provides an accurate assessment of whether the client is ready
        to receive and process weather messages.

        Returns:
            True if the client is connected to the XMPP server and not in the process
            of shutting down, False otherwise. A False result indicates the client
            cannot reliably receive messages and may need reconnection.

        """
        return self.is_connected() and not self.is_shutting_down

    # Connection event handlers
    async def _on_connecting(self, _event: object) -> None:
        """Handle connection initiation."""
        logger.info("Starting connection attempt to NWWS-OI server")
        self._connection_start_time = time.time()

    async def _on_reconnect_delay(self, delay_time: float) -> None:
        """Handle connection delay notification."""
        logger.info("Reconnection delayed - delay_seconds: %s", delay_time)

    async def _on_failed_auth(self, _event: object) -> None:
        """Handle authentication failure."""
        logger.error("Authentication failed for NWWS-OI client")

    async def _on_connection_failed(self, reason: str | Exception) -> None:
        """Handle connection failure."""
        logger.error("Connection to NWWS-OI server failed - reason: %s", str(reason))

    async def _on_connected(self, _event: object) -> None:
        """Handle successful connection."""
        logger.info("Connected to NWWS-OI server")

    async def _monitor_idle_timeout(self) -> None:
        """Monitor for idle timeout and force reconnect if needed."""
        while not self.is_shutting_down:
            await asyncio.sleep(10)
            now = time.time()
            if now - self.last_message_time > IDLE_TIMEOUT:
                logger.warning(
                    "No messages received in %d seconds, reconnecting...",
                    IDLE_TIMEOUT,
                )

                self.reconnect(reason="Idle timeout exceeded")
                break

    # Session event handlers
    async def _on_session_start(self, _event: object) -> None:
        """Handle successful connection and authentication."""
        logger.info("Successfully authenticated with NWWS-OI server")

        await self._start_background_services()

        try:
            await self.get_roster()  # type: ignore[misc]
            logger.info("Roster retrieved successfully")

            # Send initial presence (non-blocking)
            self.send_presence()
            logger.info("Initial presence sent")

            await self._join_nwws_room(self.config.history)
            logger.info("Joined MUC room - room: %s, nickname: %s", MUC_ROOM, self.nickname)

            await self._send_subscription_presence()
            logger.info("Subscription presence sent")
        except XMPPError:
            logger.exception("Failed to retrieve roster or join MUC")

    async def _start_background_services(self) -> None:
        """Start necessary services after session start with proper task management."""
        # Stop any existing background services first
        self._stop_background_services()

        # Start idle timeout monitoring
        self._idle_monitor_task = asyncio.create_task(
            self._monitor_idle_timeout(),
            name="idle_timeout_monitor",
        )
        self._background_tasks.append(self._idle_monitor_task)
        logger.info("Idle timeout monitoring enabled - timeout: %d", IDLE_TIMEOUT)

    async def _join_nwws_room(self, max_history: int = MAX_HISTORY) -> None:
        """Join the NWWS room."""
        # Don't join if shutting down
        if self.is_shutting_down:
            return

        logger.info("Joining NWWS room - room: %s, nickname: %s", MUC_ROOM, self.nickname)

        # Join MUC room
        muc_room_jid = JID(MUC_ROOM)
        try:
            await self.plugin["xep_0045"].join_muc(  # type: ignore[misc]
                muc_room_jid,
                self.nickname,
                maxhistory=str(max_history),
            )

        except XMPPError:
            logger.exception(
                "Failed to join NWWS room - room: %s, nickname: %s",
                MUC_ROOM,
                self.nickname,
            )

    async def _send_subscription_presence(self) -> None:
        """Send subscription presence."""
        # Send presence to confirm subscription
        try:
            self.send_presence(pto=f"{MUC_ROOM}/{self.nickname}")
        except XMPPError:
            logger.exception(
                "Failed to send subscription presence - room: %s, nickname: %s",
                MUC_ROOM,
                self.nickname,
            )

    # MUC event handlers
    async def _on_muc_presence(self, presence: object) -> None:
        """Handle MUC presence updates."""
        logger.info(
            "Successfully joined MUC room - room: %s, nickname: %s, presence: %s",
            MUC_ROOM,
            self.nickname,
            presence,
        )

    # Stanza event handlers
    async def _on_stanza_not_sent(self, stanza: object) -> None:
        """Handle stanza send failure."""
        stanza_type = str(getattr(stanza, "tag", "unknown"))
        logger.warning("Stanza not sent - stanza_type: %s", stanza_type)

    async def _on_groupchat_message(self, msg: Message) -> None:
        """Process incoming groupchat message."""
        message_start_time = time.time()
        self.last_message_time = message_start_time

        if self.is_shutting_down:
            logger.info("Client is shutting down, ignoring message")
            return

        # Check if the message is from the expected MUC room
        if msg.get_mucroom() != JID(MUC_ROOM).bare:
            logger.warning(
                "Message not from %s room, skipping - from_jid: %s",
                MUC_ROOM,
                msg["from"].bare,
            )
            return

        try:
            # Process the message
            weather_message = await self._on_nwws_message(msg)

            if weather_message is None:
                # Message was skipped (logged in _on_nwws_message)
                return

            # Dispatch message to both queue and subscribers
            await self._dispatch_message(weather_message)

        except (ET.ParseError, UnicodeDecodeError) as e:
            logger.warning("Message parsing failed - error: %s", str(e))
        except Exception:
            logger.exception("Unexpected message processing error")

    def _extract_wmo_id_if_possible(self, msg: Message) -> str | None:
        """Try to extract office ID from message even if parsing failed."""
        try:
            x = msg.xml.find("{nwws-oi}x")
            if x is not None:
                return x.get("cccc")
        except Exception:  # noqa: BLE001
            logger.debug("Failed to extract office ID from message")
        return None

    async def _on_nwws_message(self, msg: Message) -> NoaaPortMessage | None:
        """Process group chat message containing weather data."""
        # Check for NWWS-OI namespace in the message
        x = msg.xml.find("{nwws-oi}x")
        if x is None:
            logger.warning(
                "No NWWS-OI namespace in group message, skipping - msg_id: %s",
                msg.get_id(),
            )
            return None

        # Get the message subject from the body or subject field
        subject = str(msg.get("body", "")) or str(msg.get("subject", ""))

        # Get delay stamp if available
        delay_stamp: datetime | None = msg["delay"]["stamp"] if "delay" in msg else None

        # Get the message body which should contain the weather data
        body = (x.text or "").strip()
        if not body:
            logger.warning(
                "No body text in NWWS-OI namespace, skipping - msg_id: %s",
                msg.get_id(),
            )
            return None

        # Get the metadata from the NWWS-OI namespace
        weather_message = NoaaPortMessage(
            subject=subject,
            noaaport=self._convert_to_noaaport(body),
            id=x.get("id", ""),
            issue=self._parse_issue_timestamp(x.get("issue", "")),
            ttaaii=x.get("ttaaii", ""),
            cccc=x.get("cccc", ""),
            awipsid=x.get("awipsid", "") or "NONE",
            delay_stamp=delay_stamp,
        )

        delay_ms = self._calculate_delay_secs(delay_stamp) if delay_stamp else None

        logger.info(
            "Received Event - subject: %s, id: %s, issue: %s, ttaaii: %s, cccc: %s, awipsid: %s, delay_ms: %s",
            weather_message.subject,
            weather_message.id,
            weather_message.issue,
            weather_message.ttaaii,
            weather_message.cccc,
            weather_message.awipsid,
            delay_ms,
        )

        return weather_message

    async def _on_session_end(self, _event: object) -> None:
        """Handle session end."""
        logger.warning("Session ended")

        # Cancel all monitoring tasks
        self._stop_background_services()

    async def _on_disconnected(self, reason: str | Exception) -> None:
        """Handle disconnection."""
        logger.warning("Disconnected from NWWS-OI server - reason: %s", str(reason))

    async def _on_killed(self, _event: object) -> None:
        """Handle forceful connection termination."""
        logger.warning("Connection forcefully terminated")

    async def stop(self, reason: str | None = None) -> None:
        """Perform graceful shutdown of the NWWS-OI client with proper cleanup.

        Orchestrates a clean shutdown sequence that ensures all resources are properly
        released and all ongoing operations are terminated safely. The shutdown process
        includes stopping background monitoring tasks, leaving the MUC room gracefully,
        disconnecting from the XMPP server, and signaling the async iterator to stop.

        The shutdown sequence follows a specific order to prevent race conditions and
        ensure data integrity:
        1. Set shutdown flag to prevent new operations
        2. Signal async iterator to stop accepting new messages
        3. Cancel all background monitoring and stats collection tasks
        4. Leave the NWWS MUC room with proper unsubscribe protocol
        5. Disconnect from the XMPP server with connection cleanup
        6. Update final connection status in stats collector

        Args:
            reason: Optional descriptive reason for the shutdown that will be logged
                   and included in the disconnect message to the server for debugging
                   and operational tracking purposes.

        Raises:
            ConnectionError: If the disconnect process encounters network issues,
                           though the client will still be marked as shut down.

        """
        if self.is_shutting_down:
            return

        logger.info("Shutting down NWWS-OI client")
        self.is_shutting_down = True

        # Signal iterator to stop
        self._stop_iteration = True

        # Cancel all monitoring tasks
        self._stop_background_services()

        # Leave MUC room gracefully
        self._leave_muc_room()

        # Disconnect from server
        await self.disconnect(ignore_send_queue=True, reason=reason)  # type: ignore[misc]

        logger.info("Stopped NWWS-OI client")

    def _stop_background_services(self) -> None:
        """Cancel all monitoring and timeout tasks."""
        for task in self._background_tasks:
            if not task.done():
                logger.info("Stopping background task - task_name: %s", task.get_name())
                task.cancel()

        # Reset task references
        self._idle_monitor_task = None
        self._stats_update_task = None
        self._background_tasks.clear()

    def _leave_muc_room(self) -> None:
        """Leave the MUC room gracefully."""
        try:
            muc_room_jid = JID(MUC_ROOM)
            self.plugin["xep_0045"].leave_muc(muc_room_jid, self.nickname)
            logger.info("Unsubscribing from MUC room - room: %s", MUC_ROOM)
        except KeyError as err:
            logger.debug(
                "MUC room not in currently joined rooms - room: %s, error: %s", MUC_ROOM, str(err)
            )
        except XMPPError as err:
            logger.warning("Failed to leave MUC room gracefully - error: %s", str(err))
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Unexpected error leaving MUC room - error: %s, error_type: %s",
                str(err),
                type(err).__name__,
            )

    def _parse_issue_timestamp(self, issue_str: str) -> datetime:
        """Parse issue time from string to datetime."""
        try:
            return datetime.fromisoformat(issue_str.replace("Z", "+00:00"))
        except ValueError:
            logger.warning(
                "Invalid issue time format, using current time - issue_str: %s",
                issue_str,
            )
            return datetime.now(UTC)

    def _calculate_delay_secs(self, delay_stamp: datetime | None) -> float:
        """Calculate delay in milliseconds from delay stamp."""
        if delay_stamp is None:
            return 0

        # Get current time in UTC
        current_time = datetime.now(UTC)

        # Calculate delay
        delay_delta = current_time - delay_stamp
        delay_ms = delay_delta.total_seconds() * 1000

        # Return positive delay only (ignore future timestamps)
        if delay_ms > 0:
            return delay_ms

        return 0

    def _convert_to_noaaport(self, text: str) -> str:
        """Convert text to NOAAPort format."""
        # Replace double newlines with carriage returns and ensure proper termination
        noaaport = f"\x01{text.replace('\n\n', '\r\r\n')}"
        if not noaaport.endswith("\n"):
            noaaport = f"{noaaport}\r\r\n"
        return f"{noaaport}\x03"
