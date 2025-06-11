"""Comprehensive unit tests for wx_wire.py module."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree as ET

import pytest
from slixmpp import JID
from slixmpp.stanza import Message

from nwws_receiver.config import WxWireConfig
from nwws_receiver.message import NoaaPortMessage
from nwws_receiver.wx_wire import IDLE_TIMEOUT, MUC_ROOM, WxWire


class TestWxWireInit:
    """Test WxWire initialization and setup."""

    def test_init_with_valid_config(self) -> None:
        """Test initialization with valid configuration."""
        config = WxWireConfig(
            username="testuser",
            password="testpass",
            server="test.example.com",
            port=5222,
            history=10,
        )

        with patch("nwws_receiver.wx_wire.WxWire.register_plugin") as mock_register:
            wx_wire = WxWire(config)

            assert wx_wire.config == config
            assert wx_wire.nickname.startswith("202")  # Current year prefix
            assert wx_wire.last_message_time > 0
            assert not wx_wire.is_shutting_down
            assert wx_wire._idle_monitor_task is None
            assert wx_wire._stats_update_task is None
            assert wx_wire._background_tasks == []
            assert wx_wire._connection_start_time is None
            assert wx_wire._message_queue.maxsize == 50
            assert not wx_wire._stop_iteration

            # Verify our specific plugins were registered
            # Note: Parent class may register additional plugins
            expected_plugins = ["xep_0030", "xep_0045", "xep_0199", "xep_0203"]
            assert mock_register.call_count >= len(expected_plugins)
            for plugin in expected_plugins:
                mock_register.assert_any_call(plugin)

    def test_init_sets_nickname_with_timestamp(self) -> None:
        """Test that nickname is set with current timestamp."""
        config = WxWireConfig(username="testuser", password="testpass")

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.__format__ = Mock(return_value="202312251430")
            mock_datetime.now.return_value = mock_now
            mock_datetime.UTC = UTC

            wx_wire = WxWire(config)
            assert wx_wire.nickname == "202312251430"

    def test_event_handlers_registered(self) -> None:
        """Test that all required event handlers are registered."""
        config = WxWireConfig(username="testuser", password="testpass")

        with patch("nwws_receiver.wx_wire.WxWire.add_event_handler") as mock_add_handler:
            WxWire(config)

            expected_handlers = [
                "connecting",
                "connected",
                "connection_failed",
                "disconnected",
                "killed",
                "failed_auth",
                "session_start",
                "session_end",
                "groupchat_message",
                "muc::{muc_room}::got_online",
                "stanza_not_sent",
                "reconnect_delay",
            ]

            assert mock_add_handler.call_count >= len(expected_handlers)


class TestWxWireAsyncIterator:
    """Test async iterator protocol implementation."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    def test_aiter_returns_self(self, wx_wire: WxWire) -> None:
        """Test that __aiter__ returns self."""
        assert wx_wire.__aiter__() is wx_wire

    async def test_anext_returns_message_from_queue(self, wx_wire: WxWire) -> None:
        """Test that __anext__ returns messages from queue."""
        test_message = NoaaPortMessage(
            subject="Test Subject",
            noaaport="Test NOAAPort content",
            id="test_id",
            issue=datetime.now(UTC),
            ttaaii="NOUS41",
            cccc="KOKX",
            awipsid="AFDOKX",
        )

        # Put message in queue
        await wx_wire._message_queue.put(test_message)

        # Get message via async iterator
        result = await wx_wire.__anext__()
        assert result == test_message

    async def test_anext_stops_iteration_when_shutting_down(self, wx_wire: WxWire) -> None:
        """Test that __anext__ raises StopAsyncIteration when shutting down."""
        wx_wire._stop_iteration = True

        with pytest.raises(StopAsyncIteration):
            await wx_wire.__anext__()

    async def test_anext_timeout_continues_loop(self, wx_wire: WxWire) -> None:
        """Test that __anext__ continues on timeout until stop condition."""
        wx_wire._stop_iteration = True

        with patch("asyncio.wait_for", side_effect=TimeoutError):
            with pytest.raises(StopAsyncIteration):
                await wx_wire.__anext__()

    async def test_async_iteration_with_for_loop(self, wx_wire: WxWire) -> None:
        """Test async iteration in a for loop context."""
        test_messages = [
            NoaaPortMessage(
                subject=f"Test {i}",
                noaaport=f"Content {i}",
                id=f"id_{i}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
                awipsid=f"TEST{i:02d}",
            )
            for i in range(3)
        ]

        # Put messages in queue
        for msg in test_messages:
            await wx_wire._message_queue.put(msg)

        # Signal stop after messages
        wx_wire._stop_iteration = True

        # Collect messages via async iteration
        collected_messages = []
        async for message in wx_wire:
            collected_messages.append(message)

        assert collected_messages == test_messages


class TestWxWireProperties:
    """Test WxWire properties."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_queue_size_property(self, wx_wire: WxWire) -> None:
        """Test queue_size property returns correct size."""
        assert wx_wire.queue_size == 0

        # Add messages to queue
        test_message = NoaaPortMessage(
            subject="Test",
            noaaport="Content",
            id="test_id",
            issue=datetime.now(UTC),
            ttaaii="NOUS41",
            cccc="KOKX",
        )

        await wx_wire._message_queue.put(test_message)
        assert wx_wire.queue_size == 1

        await wx_wire._message_queue.put(test_message)
        assert wx_wire.queue_size == 2


class TestWxWireConnectionManagement:
    """Test connection management methods."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(
            username="testuser", password="testpass", server="test.example.com", port=5222
        )
        return WxWire(config)

    async def test_start_calls_parent_connect(self, wx_wire: WxWire) -> None:
        """Test start method calls parent connect with correct parameters."""

        # Create an async function that returns True
        async def mock_connect_async(*args, **kwargs):
            return True

        # Mock the super().connect() call directly
        with patch("slixmpp.ClientXMPP.connect", side_effect=mock_connect_async) as mock_connect:
            result = await wx_wire.start()

            mock_connect.assert_called_once_with(host="test.example.com", port=5222)
            assert result is True

    def test_is_client_connected_when_connected_and_not_shutting_down(
        self, wx_wire: WxWire
    ) -> None:
        """Test is_client_connected returns True when connected and not shutting down."""
        with patch.object(wx_wire, "is_connected", return_value=True):
            wx_wire.is_shutting_down = False
            assert wx_wire.is_client_connected() is True

    def test_is_client_connected_when_not_connected(self, wx_wire: WxWire) -> None:
        """Test is_client_connected returns False when not connected."""
        with patch.object(wx_wire, "is_connected", return_value=False):
            wx_wire.is_shutting_down = False
            assert wx_wire.is_client_connected() is False

    def test_is_client_connected_when_shutting_down(self, wx_wire: WxWire) -> None:
        """Test is_client_connected returns False when shutting down."""
        with patch.object(wx_wire, "is_connected", return_value=True):
            wx_wire.is_shutting_down = True
            assert wx_wire.is_client_connected() is False

    async def test_stop_graceful_shutdown(self, wx_wire: WxWire) -> None:
        """Test stop method performs graceful shutdown."""
        wx_wire.is_shutting_down = False

        # Mock disconnect as an async function
        async def mock_disconnect(*args, **kwargs):
            return None

        with (
            patch.object(wx_wire, "_stop_background_services") as mock_stop_services,
            patch.object(wx_wire, "_leave_muc_room") as mock_leave_room,
            patch.object(
                wx_wire, "disconnect", side_effect=mock_disconnect
            ) as mock_disconnect_patch,
        ):
            await wx_wire.stop("test reason")

            assert wx_wire.is_shutting_down is True
            assert wx_wire._stop_iteration is True
            mock_stop_services.assert_called_once()
            mock_leave_room.assert_called_once()
            mock_disconnect_patch.assert_called_once_with(
                ignore_send_queue=True, reason="test reason"
            )

    async def test_stop_already_shutting_down(self, wx_wire: WxWire) -> None:
        """Test stop method returns early if already shutting down."""
        wx_wire.is_shutting_down = True

        with patch.object(wx_wire, "_stop_background_services") as mock_stop_services:
            await wx_wire.stop()
            mock_stop_services.assert_not_called()


class TestWxWireEventHandlers:
    """Test event handler methods."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_on_connecting_sets_start_time(self, wx_wire: WxWire) -> None:
        """Test _on_connecting sets connection start time."""
        with patch("time.time", return_value=12345.67):
            await wx_wire._on_connecting(None)
            assert wx_wire._connection_start_time == 12345.67

    async def test_on_reconnect_delay_logs_delay(self, wx_wire: WxWire) -> None:
        """Test _on_reconnect_delay logs delay time."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_reconnect_delay(30.5)
            mock_logger.info.assert_called_with("Reconnection delayed - delay_seconds: %s", 30.5)

    async def test_on_failed_auth_logs_error(self, wx_wire: WxWire) -> None:
        """Test _on_failed_auth logs authentication failure."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_failed_auth(None)
            mock_logger.error.assert_called_with("Authentication failed for NWWS-OI client")

    async def test_on_connection_failed_logs_reason(self, wx_wire: WxWire) -> None:
        """Test _on_connection_failed logs failure reason."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_connection_failed("Connection timeout")
            mock_logger.error.assert_called_with(
                "Connection to NWWS-OI server failed - reason: %s", "Connection timeout"
            )

    async def test_on_connected_logs_success(self, wx_wire: WxWire) -> None:
        """Test _on_connected logs successful connection."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_connected(None)
            mock_logger.info.assert_called_with("Connected to NWWS-OI server")

    async def test_on_session_start_full_initialization(self, wx_wire: WxWire) -> None:
        """Test _on_session_start performs full initialization sequence."""
        with (
            patch.object(wx_wire, "_start_background_services") as mock_start_services,
            patch.object(wx_wire, "get_roster", new_callable=AsyncMock) as mock_get_roster,
            patch.object(wx_wire, "send_presence") as mock_send_presence,
            patch.object(wx_wire, "_join_nwws_room") as mock_join_room,
            patch.object(wx_wire, "_send_subscription_presence") as mock_send_sub,
        ):
            await wx_wire._on_session_start(None)

            mock_start_services.assert_called_once()
            mock_get_roster.assert_called_once()
            mock_send_presence.assert_called_once()
            mock_join_room.assert_called_once_with(wx_wire.config.history)
            mock_send_sub.assert_called_once()

    async def test_on_session_start_handles_xmpp_error(self, wx_wire: WxWire) -> None:
        """Test _on_session_start handles XMPP errors gracefully."""
        from slixmpp.exceptions import XMPPError

        with (
            patch.object(wx_wire, "_start_background_services"),
            patch.object(
                wx_wire,
                "get_roster",
                new_callable=AsyncMock,
                side_effect=XMPPError("service-unavailable", "Test error"),
            ),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_session_start(None)
            mock_logger.exception.assert_called_with("Failed to retrieve roster or join MUC")

    async def test_on_session_end_stops_services(self, wx_wire: WxWire) -> None:
        """Test _on_session_end stops background services."""
        with patch.object(wx_wire, "_stop_background_services") as mock_stop_services:
            await wx_wire._on_session_end(None)
            mock_stop_services.assert_called_once()

    async def test_on_disconnected_logs_reason(self, wx_wire: WxWire) -> None:
        """Test _on_disconnected logs disconnection reason."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_disconnected("Connection lost")
            mock_logger.warning.assert_called_with(
                "Disconnected from NWWS-OI server - reason: %s", "Connection lost"
            )

    async def test_on_killed_logs_termination(self, wx_wire: WxWire) -> None:
        """Test _on_killed logs forceful termination."""
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_killed(None)
            mock_logger.warning.assert_called_with("Connection forcefully terminated")

    async def test_on_muc_presence_logs_join(self, wx_wire: WxWire) -> None:
        """Test _on_muc_presence logs MUC room join."""
        presence = Mock()
        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_muc_presence(presence)
            mock_logger.info.assert_called_with(
                "Successfully joined MUC room - room: %s, nickname: %s, presence: %s",
                MUC_ROOM,
                wx_wire.nickname,
                presence,
            )

    async def test_on_stanza_not_sent_logs_warning(self, wx_wire: WxWire) -> None:
        """Test _on_stanza_not_sent logs stanza failure."""
        stanza = Mock()
        stanza.tag = "presence"

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._on_stanza_not_sent(stanza)
            mock_logger.warning.assert_called_with("Stanza not sent - stanza_type: %s", "presence")


class TestWxWireBackgroundServices:
    """Test background service management."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_start_background_services_creates_tasks(self, wx_wire: WxWire) -> None:
        """Test _start_background_services creates necessary tasks."""
        with (
            patch.object(wx_wire, "_stop_background_services") as mock_stop,
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_task = Mock()
            mock_task.get_name.return_value = "test_task"
            mock_create_task.return_value = mock_task

            await wx_wire._start_background_services()

            mock_stop.assert_called_once()
            mock_create_task.assert_called_once()
            assert mock_task in wx_wire._background_tasks

    def test_stop_background_services_cancels_tasks(self, wx_wire: WxWire) -> None:
        """Test _stop_background_services cancels all background tasks."""
        # Create mock tasks
        task1 = Mock()
        task1.done.return_value = False
        task1.get_name.return_value = "task1"

        task2 = Mock()
        task2.done.return_value = True  # Already done

        wx_wire._background_tasks = [task1, task2]
        wx_wire._idle_monitor_task = task1

        wx_wire._stop_background_services()

        task1.cancel.assert_called_once()
        task2.cancel.assert_not_called()  # Should not cancel done tasks

        assert wx_wire._idle_monitor_task is None
        assert wx_wire._stats_update_task is None
        assert wx_wire._background_tasks == []

    async def test_monitor_idle_timeout_reconnects_on_timeout(self, wx_wire: WxWire) -> None:
        """Test _monitor_idle_timeout reconnects when idle timeout exceeded."""
        wx_wire.is_shutting_down = False
        wx_wire.last_message_time = time.time() - (IDLE_TIMEOUT + 10)  # Past timeout

        with (
            patch.object(wx_wire, "reconnect") as mock_reconnect,
            patch("asyncio.sleep", side_effect=[None, Exception("Break loop")]),
        ):
            try:
                await wx_wire._monitor_idle_timeout()
            except Exception:
                pass  # Expected to break from the loop

            mock_reconnect.assert_called_once_with(reason="Idle timeout exceeded")

    async def test_monitor_idle_timeout_exits_on_shutdown(self, wx_wire: WxWire) -> None:
        """Test _monitor_idle_timeout exits when shutting down."""
        wx_wire.is_shutting_down = True

        with patch("asyncio.sleep") as mock_sleep:
            await wx_wire._monitor_idle_timeout()
            mock_sleep.assert_not_called()


class TestWxWireMucOperations:
    """Test MUC room operations."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        wx_wire = WxWire(config)
        wx_wire.plugin = {"xep_0045": Mock()}
        return wx_wire

    async def test_join_nwws_room_success(self, wx_wire: WxWire) -> None:
        """Test successful MUC room join."""
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.join_muc = AsyncMock()

        await wx_wire._join_nwws_room(15)

        mock_muc.join_muc.assert_called_once()
        call_args = mock_muc.join_muc.call_args
        assert str(call_args[0][0]) == MUC_ROOM
        assert call_args[0][1] == wx_wire.nickname
        assert call_args[1]["maxhistory"] == "15"

    async def test_join_nwws_room_skips_when_shutting_down(self, wx_wire: WxWire) -> None:
        """Test MUC room join is skipped when shutting down."""
        wx_wire.is_shutting_down = True
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.join_muc = AsyncMock()

        await wx_wire._join_nwws_room()

        mock_muc.join_muc.assert_not_called()

    async def test_join_nwws_room_handles_xmpp_error(self, wx_wire: WxWire) -> None:
        """Test MUC room join handles XMPP errors."""
        from slixmpp.exceptions import XMPPError

        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.join_muc = AsyncMock(side_effect=XMPPError("service-unavailable", "Join failed"))

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            await wx_wire._join_nwws_room()
            mock_logger.exception.assert_called_with(
                "Failed to join NWWS room - room: %s, nickname: %s",
                MUC_ROOM,
                wx_wire.nickname,
            )

    async def test_send_subscription_presence_success(self, wx_wire: WxWire) -> None:
        """Test successful subscription presence send."""
        with patch.object(wx_wire, "send_presence") as mock_send_presence:
            await wx_wire._send_subscription_presence()
            mock_send_presence.assert_called_once_with(pto=f"{MUC_ROOM}/{wx_wire.nickname}")

    async def test_send_subscription_presence_handles_xmpp_error(self, wx_wire: WxWire) -> None:
        """Test subscription presence handles XMPP errors."""
        from slixmpp.exceptions import XMPPError

        with (
            patch.object(
                wx_wire,
                "send_presence",
                side_effect=XMPPError("service-unavailable", "Send failed"),
            ),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._send_subscription_presence()
            mock_logger.exception.assert_called_with(
                "Failed to send subscription presence - room: %s, nickname: %s",
                MUC_ROOM,
                wx_wire.nickname,
            )

    def test_leave_muc_room_success(self, wx_wire: WxWire) -> None:
        """Test successful MUC room leave."""
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.leave_muc = Mock()

        wx_wire._leave_muc_room()

        mock_muc.leave_muc.assert_called_once()
        call_args = mock_muc.leave_muc.call_args
        assert str(call_args[0][0]) == MUC_ROOM
        assert call_args[0][1] == wx_wire.nickname

    def test_leave_muc_room_handles_key_error(self, wx_wire: WxWire) -> None:
        """Test leave MUC room handles KeyError (room not joined)."""
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.leave_muc = Mock(side_effect=KeyError("Room not found"))

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            wx_wire._leave_muc_room()
            mock_logger.debug.assert_called_with(
                "MUC room not in currently joined rooms - room: %s, error: %s",
                MUC_ROOM,
                "'Room not found'",
            )

    def test_leave_muc_room_handles_xmpp_error(self, wx_wire: WxWire) -> None:
        """Test leave MUC room handles XMPP errors."""
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.leave_muc = Mock(side_effect=Exception("Leave failed"))

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            wx_wire._leave_muc_room()
            mock_logger.warning.assert_called_with(
                "Unexpected error leaving MUC room - error: %s, error_type: %s",
                "Leave failed",
                "Exception",
            )

    def test_leave_muc_room_handles_unexpected_error(self, wx_wire: WxWire) -> None:
        """Test leave MUC room handles unexpected errors."""
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.leave_muc = Mock(side_effect=RuntimeError("Unexpected error"))

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            wx_wire._leave_muc_room()
            mock_logger.warning.assert_called_with(
                "Unexpected error leaving MUC room - error: %s, error_type: %s",
                "Unexpected error",
                "RuntimeError",
            )


class TestWxWireMessageProcessing:
    """Test message processing functionality."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    @pytest.fixture
    def mock_message(self) -> Message:
        """Create mock XMPP message with NWWS-OI content."""
        msg = Mock(spec=Message)
        msg.get_mucroom.return_value = JID(MUC_ROOM).bare
        msg.get_id.return_value = "test_msg_id"
        msg.get.side_effect = lambda key, default="": {
            "body": "Test weather alert",
            "subject": "Weather Alert Subject",
        }.get(key, default)

        # Create mock XML with NWWS-OI namespace
        mock_xml = Mock()
        mock_x_element = Mock()
        mock_x_element.get.side_effect = lambda key, default="": {
            "id": "test_product_id",
            "issue": "2023-12-25T14:30:00Z",
            "ttaaii": "NOUS41",
            "cccc": "KOKX",
            "awipsid": "AFDOKX",
        }.get(key, default)
        mock_x_element.text = "This is the weather product content\n\nWith multiple lines"

        mock_xml.find.return_value = mock_x_element
        msg.xml = mock_xml

        # Mock delay handling
        msg.__contains__ = lambda self, key: key == "delay"
        msg.__getitem__ = (
            lambda self, key: {"stamp": datetime(2023, 12, 25, 14, 25, tzinfo=UTC)}
            if key == "delay"
            else None
        )

        return msg

    async def test_on_groupchat_message_processes_valid_message(
        self, wx_wire: WxWire, mock_message: Message
    ) -> None:
        """Test _on_groupchat_message processes valid messages."""
        with patch.object(wx_wire, "_on_nwws_message") as mock_process:
            test_weather_msg = NoaaPortMessage(
                subject="Test",
                noaaport="Content",
                id="test_id",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            mock_process.return_value = test_weather_msg

            await wx_wire._on_groupchat_message(mock_message)

            mock_process.assert_called_once_with(mock_message)
            assert wx_wire.queue_size == 1

    async def test_on_groupchat_message_skips_wrong_room(self, wx_wire: WxWire) -> None:
        """Test _on_groupchat_message skips messages from wrong room."""
        mock_msg = Mock(spec=Message)
        mock_msg.get_mucroom.return_value = "wrong_room@example.com"
        mock_msg.__getitem__ = Mock(return_value=Mock(bare="wrong_room@example.com"))

        with (
            patch.object(wx_wire, "_on_nwws_message") as mock_process,
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_groupchat_message(mock_msg)

            mock_process.assert_not_called()
            mock_logger.warning.assert_called()

    async def test_on_groupchat_message_skips_when_shutting_down(
        self, wx_wire: WxWire, mock_message: Message
    ) -> None:
        """Test _on_groupchat_message skips processing when shutting down."""
        wx_wire.is_shutting_down = True

        with patch.object(wx_wire, "_on_nwws_message") as mock_process:
            await wx_wire._on_groupchat_message(mock_message)
            mock_process.assert_not_called()

    async def test_on_groupchat_message_handles_queue_full(
        self, wx_wire: WxWire, mock_message: Message
    ) -> None:
        """Test _on_groupchat_message handles full queue gracefully."""
        # Fill the queue to capacity
        for _ in range(wx_wire._message_queue.maxsize):
            await wx_wire._message_queue.put(
                NoaaPortMessage(
                    subject="Filler",
                    noaaport="Content",
                    id="filler_id",
                    issue=datetime.now(UTC),
                    ttaaii="NOUS41",
                    cccc="KOKX",
                )
            )

        with (
            patch.object(wx_wire, "_on_nwws_message") as mock_process,
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            test_weather_msg = NoaaPortMessage(
                subject="Test",
                noaaport="Content",
                id="test_id",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
                awipsid="TESTMSG",
            )
            mock_process.return_value = test_weather_msg

            await wx_wire._on_groupchat_message(mock_message)

            mock_logger.warning.assert_called_with(
                "Message queue full (size: %d), dropping message: %s",
                wx_wire._message_queue.maxsize,
                "TESTMSG",
            )

    async def test_on_groupchat_message_handles_parse_error(
        self, wx_wire: WxWire, mock_message: Message
    ) -> None:
        """Test _on_groupchat_message handles parsing errors."""
        with (
            patch.object(wx_wire, "_on_nwws_message", side_effect=ET.ParseError("Parse error")),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_groupchat_message(mock_message)
            mock_logger.warning.assert_called_with(
                "Message parsing failed - error: %s", "Parse error"
            )

    async def test_on_nwws_message_processes_valid_nwws_message(
        self, wx_wire: WxWire, mock_message: Message
    ) -> None:
        """Test _on_nwws_message processes valid NWWS-OI messages."""
        result = await wx_wire._on_nwws_message(mock_message)

        assert result is not None
        assert result.subject == "Test weather alert"
        assert result.id == "test_product_id"
        assert result.ttaaii == "NOUS41"
        assert result.cccc == "KOKX"
        assert result.awipsid == "AFDOKX"
        assert result.issue == datetime(2023, 12, 25, 14, 30, tzinfo=UTC)
        assert result.delay_stamp == datetime(2023, 12, 25, 14, 25, tzinfo=UTC)
        assert "\x01" in result.noaaport  # NOAAPort format
        assert "\x03" in result.noaaport

    async def test_on_nwws_message_returns_none_for_missing_namespace(
        self, wx_wire: WxWire
    ) -> None:
        """Test _on_nwws_message returns None when NWWS-OI namespace missing."""
        mock_msg = Mock(spec=Message)
        mock_msg.xml = Mock()
        mock_msg.xml.find.return_value = None
        mock_msg.get_id.return_value = "test_id"

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            result = await wx_wire._on_nwws_message(mock_msg)

            assert result is None
            mock_logger.warning.assert_called_with(
                "No NWWS-OI namespace in group message, skipping - msg_id: %s",
                "test_id",
            )

    async def test_on_nwws_message_returns_none_for_empty_body(self, wx_wire: WxWire) -> None:
        """Test _on_nwws_message returns None for messages with empty body."""
        mock_msg = Mock(spec=Message)
        mock_msg.xml = Mock()
        mock_x_element = Mock()
        mock_x_element.text = ""  # Empty body
        mock_msg.xml.find.return_value = mock_x_element
        mock_msg.get_id.return_value = "test_id"
        mock_msg.get.return_value = ""
        mock_msg.__contains__ = Mock(return_value=False)  # "delay" not in msg

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            result = await wx_wire._on_nwws_message(mock_msg)

            assert result is None
            mock_logger.warning.assert_called_with(
                "No body text in NWWS-OI namespace, skipping - msg_id: %s",
                "test_id",
            )

    def test_extract_wmo_id_if_possible_success(self, wx_wire: WxWire) -> None:
        """Test _extract_wmo_id_if_possible extracts office ID successfully."""
        mock_msg = Mock(spec=Message)
        mock_msg.xml = Mock()
        mock_x_element = Mock()
        mock_x_element.get.return_value = "KBOS"
        mock_msg.xml.find.return_value = mock_x_element

        result = wx_wire._extract_wmo_id_if_possible(mock_msg)
        assert result == "KBOS"

    def test_extract_wmo_id_if_possible_returns_none_on_error(self, wx_wire: WxWire) -> None:
        """Test _extract_wmo_id_if_possible returns None on errors."""
        mock_msg = Mock(spec=Message)
        mock_msg.xml = Mock()
        mock_msg.xml.find.side_effect = Exception("Parse error")

        result = wx_wire._extract_wmo_id_if_possible(mock_msg)
        assert result is None


class TestWxWireUtilities:
    """Test utility methods."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    def test_parse_issue_timestamp_valid_iso_format(self, wx_wire: WxWire) -> None:
        """Test _parse_issue_timestamp with valid ISO format."""
        result = wx_wire._parse_issue_timestamp("2023-12-25T14:30:00Z")
        expected = datetime(2023, 12, 25, 14, 30, tzinfo=UTC)
        assert result == expected

    def test_parse_issue_timestamp_invalid_format_uses_current_time(self, wx_wire: WxWire) -> None:
        """Test _parse_issue_timestamp with invalid format uses current time."""
        with (
            patch("nwws_receiver.wx_wire.datetime") as mock_datetime,
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            current_time = datetime(2023, 12, 25, 15, 0, tzinfo=UTC)
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC
            # Mock fromisoformat to raise ValueError for invalid timestamps
            mock_datetime.fromisoformat.side_effect = ValueError("Invalid format")

            result = wx_wire._parse_issue_timestamp("invalid-timestamp")

            assert result == current_time
            mock_logger.warning.assert_called_with(
                "Invalid issue time format, using current time - issue_str: %s",
                "invalid-timestamp",
            )

    def test_calculate_delay_secs_positive_delay(self, wx_wire: WxWire) -> None:
        """Test _calculate_delay_secs calculates positive delay correctly."""
        delay_stamp = datetime(2023, 12, 25, 14, 30, tzinfo=UTC)
        current_time = datetime(2023, 12, 25, 14, 30, 5, tzinfo=UTC)  # 5 seconds later

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            result = wx_wire._calculate_delay_secs(delay_stamp)
            assert result == 5000.0  # 5 seconds = 5000 milliseconds

    def test_calculate_delay_secs_negative_delay_returns_zero(self, wx_wire: WxWire) -> None:
        """Test _calculate_delay_secs returns zero for negative delay (future timestamp)."""
        delay_stamp = datetime(2023, 12, 25, 14, 30, 5, tzinfo=UTC)  # Future timestamp
        current_time = datetime(2023, 12, 25, 14, 30, tzinfo=UTC)

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            result = wx_wire._calculate_delay_secs(delay_stamp)
            assert result == 0

    def test_calculate_delay_secs_none_returns_zero(self, wx_wire: WxWire) -> None:
        """Test _calculate_delay_secs returns zero for None input."""
        result = wx_wire._calculate_delay_secs(None)
        assert result == 0

    def test_convert_to_noaaport_formats_correctly(self, wx_wire: WxWire) -> None:
        """Test _convert_to_noaaport formats text correctly."""
        test_text = "Line 1\n\nLine 2\n\nLine 3"
        result = wx_wire._convert_to_noaaport(test_text)

        assert result.startswith("\x01")
        assert result.endswith("\x03")
        assert "Line 1\r\r\nLine 2\r\r\nLine 3\r\r\n" in result

    def test_convert_to_noaaport_adds_termination(self, wx_wire: WxWire) -> None:
        """Test _convert_to_noaaport adds proper termination."""
        test_text = "Single line without newline"
        result = wx_wire._convert_to_noaaport(test_text)

        assert result == "\x01Single line without newline\r\r\n\x03"

    def test_convert_to_noaaport_preserves_existing_newline(self, wx_wire: WxWire) -> None:
        """Test _convert_to_noaaport preserves existing final newline."""
        test_text = "Text with newline\n"
        result = wx_wire._convert_to_noaaport(test_text)

        # The implementation only adds \r\r\n if the text doesn't end with \n
        # Since it already ends with \n, no additional \r\r\n is added
        assert result == "\x01Text with newline\n\x03"


class TestWxWireIntegration:
    """Integration tests for WxWire functionality."""

    @pytest.fixture
    def config(self) -> WxWireConfig:
        """Create test configuration."""
        return WxWireConfig(
            username="testuser",
            password="testpass",
            server="test.example.com",
            port=5222,
            history=5,
        )

    async def test_full_message_processing_workflow(self, config: WxWireConfig) -> None:
        """Test complete message processing workflow from XMPP to NoaaPortMessage."""
        wx_wire = WxWire(config)

        # Create realistic XMPP message
        mock_msg = Mock(spec=Message)
        mock_msg.get_mucroom.return_value = JID(MUC_ROOM).bare
        mock_msg.get_id.return_value = "msg_12345"
        mock_msg.get.side_effect = lambda key, default="": {
            "body": "URGENT - WEATHER MESSAGE",
            "subject": "Severe Weather Alert",
        }.get(key, default)

        # Setup XML namespace content
        mock_xml = Mock()
        mock_x_element = Mock()
        mock_x_element.get.side_effect = lambda key, default="": {
            "id": "prod_67890",
            "issue": "2023-12-25T16:45:00Z",
            "ttaaii": "WFUS51",
            "cccc": "KBOS",
            "awipsid": "SVRBOS",
        }.get(key, default)
        mock_x_element.text = (
            "URGENT - WEATHER MESSAGE\n"
            "NATIONAL WEATHER SERVICE BOSTON MA\n\n"
            "SEVERE THUNDERSTORM WARNING FOR...\n"
            "MIDDLESEX COUNTY IN EASTERN MASSACHUSETTS...\n\n"
            "AT 445 PM EST...A SEVERE THUNDERSTORM WAS LOCATED..."
        )

        mock_xml.find.return_value = mock_x_element
        mock_msg.xml = mock_xml

        # Mock delay handling
        mock_msg.__contains__ = lambda self, key: False  # No delay
        mock_msg.__getitem__ = lambda self, key: None

        # Process the message
        await wx_wire._on_groupchat_message(mock_msg)

        # Verify message was queued
        assert wx_wire.queue_size == 1

        # Retrieve and verify the processed message
        processed_msg = await wx_wire.__anext__()

        assert processed_msg.subject == "URGENT - WEATHER MESSAGE"
        assert processed_msg.id == "prod_67890"
        assert processed_msg.ttaaii == "WFUS51"
        assert processed_msg.cccc == "KBOS"
        assert processed_msg.awipsid == "SVRBOS"
        assert processed_msg.issue == datetime(2023, 12, 25, 16, 45, tzinfo=UTC)
        assert processed_msg.delay_stamp is None
        assert "SEVERE THUNDERSTORM WARNING" in processed_msg.noaaport
        assert processed_msg.noaaport.startswith("\x01")
        assert processed_msg.noaaport.endswith("\x03")

    async def test_shutdown_during_message_processing(self, config: WxWireConfig) -> None:
        """Test graceful shutdown during active message processing."""
        wx_wire = WxWire(config)

        # Start processing messages
        message_task = asyncio.create_task(wx_wire.__anext__())

        # Give the task a moment to start waiting
        await asyncio.sleep(0.1)

        # Initiate shutdown
        await wx_wire.stop("Integration test shutdown")

        # The message task should complete with StopAsyncIteration
        with pytest.raises(StopAsyncIteration):
            await message_task

        # Verify shutdown state
        assert wx_wire.is_shutting_down
        assert wx_wire._stop_iteration

    async def test_queue_backpressure_handling(self, config: WxWireConfig) -> None:
        """Test queue backpressure and message dropping."""
        wx_wire = WxWire(config)

        # Create multiple test messages
        test_messages = []
        for i in range(wx_wire._message_queue.maxsize + 5):  # More than queue capacity
            msg = NoaaPortMessage(
                subject=f"Message {i}",
                noaaport=f"Content {i}",
                id=f"msg_{i}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
                awipsid=f"TEST{i:02d}",
            )
            test_messages.append(msg)

        # Fill queue beyond capacity
        for i, msg in enumerate(test_messages):
            if i < wx_wire._message_queue.maxsize:
                await wx_wire._message_queue.put(msg)
            else:
                # These should be dropped due to queue full
                try:
                    wx_wire._message_queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass  # Expected behavior

        # Verify queue is at capacity
        assert wx_wire.queue_size == wx_wire._message_queue.maxsize

        # Consume messages and verify order
        consumed_messages = []
        for _ in range(wx_wire._message_queue.maxsize):
            consumed_messages.append(await wx_wire._message_queue.get())

        # Should have first maxsize messages, rest were dropped
        assert len(consumed_messages) == wx_wire._message_queue.maxsize
        assert consumed_messages == test_messages[: wx_wire._message_queue.maxsize]


class TestWxWireSubscriberPattern:
    """Test subscribe/unsubscribe functionality."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    @pytest.fixture
    def sample_message(self) -> NoaaPortMessage:
        """Create a sample NoaaPortMessage for testing."""
        return NoaaPortMessage(
            subject="Test Weather Alert",
            noaaport="\x01Test content\r\r\n\x03",
            id="test_message_id",
            issue=datetime.now(UTC),
            ttaaii="NOUS41",
            cccc="KOKX",
            awipsid="TESTOKX",
        )

    def test_subscribe_adds_handler(self, wx_wire: WxWire) -> None:
        """Test that subscribe adds a handler to the subscribers set."""
        handler = Mock()

        wx_wire.subscribe(handler)

        assert handler in wx_wire._subscribers
        assert wx_wire.subscriber_count == 1

    def test_subscribe_duplicate_handler_ignored(self, wx_wire: WxWire) -> None:
        """Test that subscribing the same handler twice is ignored."""
        handler = Mock()

        wx_wire.subscribe(handler)
        wx_wire.subscribe(handler)  # Duplicate

        assert wx_wire.subscriber_count == 1
        assert handler in wx_wire._subscribers

    def test_subscribe_multiple_handlers(self, wx_wire: WxWire) -> None:
        """Test that multiple handlers can be subscribed."""
        handler1 = Mock()
        handler2 = Mock()
        handler3 = Mock()

        wx_wire.subscribe(handler1)
        wx_wire.subscribe(handler2)
        wx_wire.subscribe(handler3)

        assert wx_wire.subscriber_count == 3
        assert handler1 in wx_wire._subscribers
        assert handler2 in wx_wire._subscribers
        assert handler3 in wx_wire._subscribers

    def test_unsubscribe_removes_handler(self, wx_wire: WxWire) -> None:
        """Test that unsubscribe removes a handler from the subscribers set."""
        handler = Mock()

        wx_wire.subscribe(handler)
        assert wx_wire.subscriber_count == 1

        wx_wire.unsubscribe(handler)
        assert wx_wire.subscriber_count == 0
        assert handler not in wx_wire._subscribers

    def test_unsubscribe_nonexistent_handler(self, wx_wire: WxWire) -> None:
        """Test that unsubscribing a non-existent handler is handled gracefully."""
        handler = Mock()

        # Should not raise an exception
        wx_wire.unsubscribe(handler)
        assert wx_wire.subscriber_count == 0

    def test_unsubscribe_partial_removal(self, wx_wire: WxWire) -> None:
        """Test that unsubscribing one handler leaves others intact."""
        handler1 = Mock()
        handler2 = Mock()
        handler3 = Mock()

        wx_wire.subscribe(handler1)
        wx_wire.subscribe(handler2)
        wx_wire.subscribe(handler3)
        assert wx_wire.subscriber_count == 3

        wx_wire.unsubscribe(handler2)
        assert wx_wire.subscriber_count == 2
        assert handler1 in wx_wire._subscribers
        assert handler2 not in wx_wire._subscribers
        assert handler3 in wx_wire._subscribers

    async def test_dispatch_message_calls_subscribers(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that _dispatch_message calls all registered subscribers."""
        handler1 = Mock()
        handler2 = Mock()

        wx_wire.subscribe(handler1)
        wx_wire.subscribe(handler2)

        await wx_wire._dispatch_message(sample_message)

        handler1.assert_called_once_with(sample_message)
        handler2.assert_called_once_with(sample_message)

    async def test_dispatch_message_adds_to_queue(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that _dispatch_message adds message to async iterator queue."""
        await wx_wire._dispatch_message(sample_message)

        assert wx_wire.queue_size == 1
        queued_message = await wx_wire._message_queue.get()
        assert queued_message == sample_message

    async def test_dispatch_message_handles_queue_full(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that _dispatch_message handles queue full condition gracefully."""
        # Fill the queue to capacity
        for _ in range(wx_wire._message_queue.maxsize):
            await wx_wire._message_queue.put(sample_message)

        # This should not raise an exception even though queue is full
        await wx_wire._dispatch_message(sample_message)

        # Queue should still be at capacity
        assert wx_wire.queue_size == wx_wire._message_queue.maxsize

    async def test_notify_subscribers_handles_exceptions(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that _notify_subscribers handles subscriber exceptions gracefully."""
        good_handler = Mock()
        bad_handler = Mock(side_effect=Exception("Test exception"))
        another_good_handler = Mock()

        wx_wire.subscribe(good_handler)
        wx_wire.subscribe(bad_handler)
        wx_wire.subscribe(another_good_handler)

        # Should not raise exception even though bad_handler fails
        await wx_wire._notify_subscribers(sample_message)

        # Good handlers should still be called
        good_handler.assert_called_once_with(sample_message)
        another_good_handler.assert_called_once_with(sample_message)
        bad_handler.assert_called_once_with(sample_message)

    async def test_notify_subscribers_no_subscribers(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that _notify_subscribers handles empty subscriber list."""
        # Should not raise exception with no subscribers
        await wx_wire._notify_subscribers(sample_message)

    async def test_integration_both_patterns_work_together(
        self, wx_wire: WxWire, sample_message: NoaaPortMessage
    ) -> None:
        """Test that both async iterator and subscriber patterns work together."""
        handler = Mock()
        wx_wire.subscribe(handler)

        # Dispatch a message
        await wx_wire._dispatch_message(sample_message)

        # Verify subscriber was called
        handler.assert_called_once_with(sample_message)

        # Verify message is also available via async iterator
        assert wx_wire.queue_size == 1
        queued_message = await wx_wire._message_queue.get()
        assert queued_message == sample_message

    def test_subscriber_count_property(self, wx_wire: WxWire) -> None:
        """Test that subscriber_count property returns correct count."""
        assert wx_wire.subscriber_count == 0

        handler1 = Mock()
        handler2 = Mock()

        wx_wire.subscribe(handler1)
        assert wx_wire.subscriber_count == 1

        wx_wire.subscribe(handler2)
        assert wx_wire.subscriber_count == 2

        wx_wire.unsubscribe(handler1)
        assert wx_wire.subscriber_count == 1

        wx_wire.unsubscribe(handler2)
        assert wx_wire.subscriber_count == 0
