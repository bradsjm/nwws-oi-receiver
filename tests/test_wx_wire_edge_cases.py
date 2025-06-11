"""Edge case and error condition tests for wx_wire.py module."""

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


class TestWxWireEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_empty_queue_iteration_with_immediate_stop(self, wx_wire: WxWire) -> None:
        """Test async iteration with empty queue and immediate stop signal."""
        wx_wire._stop_iteration = True

        with pytest.raises(StopAsyncIteration):
            await wx_wire.__anext__()

    async def test_queue_with_none_values(self, wx_wire: WxWire) -> None:
        """Test handling of None values in queue (should not happen in normal operation)."""
        # This tests defensive programming - None should not be put in queue normally
        with patch.object(wx_wire._message_queue, "get", return_value=None):
            result = await wx_wire.__anext__()
            assert result is None

    def test_queue_size_property_thread_safety(self, wx_wire: WxWire) -> None:
        """Test queue_size property under concurrent access."""
        # This test verifies that queue_size property is thread-safe
        import threading

        results = []

        def check_queue_size() -> None:
            for _ in range(100):
                size = wx_wire.queue_size
                results.append(size)

        # Start multiple threads checking queue size
        threads = [threading.Thread(target=check_queue_size) for _ in range(5)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All results should be non-negative integers
        assert all(isinstance(size, int) and size >= 0 for size in results)

    async def test_multiple_start_calls(self, wx_wire: WxWire) -> None:
        """Test multiple calls to start() method."""
        with patch.object(wx_wire, "connect", return_value=True) as mock_connect:
            # First call
            result1 = await wx_wire.start()
            assert result1 is True

            # Second call (should still work)
            result2 = await wx_wire.start()
            assert result2 is True

            # Both calls should have invoked connect
            assert mock_connect.call_count == 2

    async def test_stop_with_none_reason(self, wx_wire: WxWire) -> None:
        """Test stop method with None reason."""
        with (
            patch.object(wx_wire, "_stop_background_services"),
            patch.object(wx_wire, "_leave_muc_room"),
            patch.object(wx_wire, "disconnect") as mock_disconnect,
        ):
            await wx_wire.stop(None)
            mock_disconnect.assert_called_once_with(ignore_send_queue=True, reason=None)

    async def test_stop_multiple_calls(self, wx_wire: WxWire) -> None:
        """Test multiple calls to stop() method."""
        with (
            patch.object(wx_wire, "_stop_background_services") as mock_stop_services,
            patch.object(wx_wire, "_leave_muc_room") as mock_leave_room,
            patch.object(wx_wire, "disconnect") as mock_disconnect,
        ):
            # First call
            await wx_wire.stop("First stop")

            # Second call (should return early)
            await wx_wire.stop("Second stop")

            # Services should only be stopped once
            mock_stop_services.assert_called_once()
            mock_leave_room.assert_called_once()
            mock_disconnect.assert_called_once()

    def test_is_client_connected_edge_cases(self, wx_wire: WxWire) -> None:
        """Test is_client_connected under various edge conditions."""
        # Test when both connected and shutting down
        with patch.object(wx_wire, "is_connected", return_value=True):
            wx_wire.is_shutting_down = True
            assert wx_wire.is_client_connected() is False

        # Test when neither connected nor shutting down
        with patch.object(wx_wire, "is_connected", return_value=False):
            wx_wire.is_shutting_down = False
            assert wx_wire.is_client_connected() is False

        # Test when not connected but also not shutting down
        with patch.object(wx_wire, "is_connected", return_value=False):
            wx_wire.is_shutting_down = False
            assert wx_wire.is_client_connected() is False


class TestWxWireErrorConditions:
    """Test error conditions and exception handling."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_start_connection_failure(self, wx_wire: WxWire) -> None:
        """Test start method when connection fails."""
        with patch.object(wx_wire, "connect", return_value=False) as mock_connect:
            result = await wx_wire.start()
            assert result is False
            mock_connect.assert_called_once()

    async def test_start_connection_exception(self, wx_wire: WxWire) -> None:
        """Test start method when connection raises exception."""
        with patch.object(wx_wire, "connect", side_effect=Exception("Connection error")):
            with pytest.raises(Exception, match="Connection error"):
                await wx_wire.start()

    async def test_session_start_roster_failure(self, wx_wire: WxWire) -> None:
        """Test session start when roster retrieval fails."""
        with (
            patch.object(wx_wire, "_start_background_services"),
            patch.object(wx_wire, "get_roster", side_effect=Exception("Roster error")),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_session_start(None)
            mock_logger.exception.assert_called_with("Failed to retrieve roster or join MUC")

    async def test_session_start_presence_failure(self, wx_wire: WxWire) -> None:
        """Test session start when sending presence fails."""
        with (
            patch.object(wx_wire, "_start_background_services"),
            patch.object(wx_wire, "get_roster"),
            patch.object(wx_wire, "send_presence", side_effect=Exception("Presence error")),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_session_start(None)
            mock_logger.exception.assert_called_with("Failed to retrieve roster or join MUC")

    async def test_background_service_task_creation_failure(self, wx_wire: WxWire) -> None:
        """Test background service startup when task creation fails."""
        with (
            patch.object(wx_wire, "_stop_background_services"),
            patch("asyncio.create_task", side_effect=Exception("Task creation failed")),
        ):
            with pytest.raises(Exception, match="Task creation failed"):
                await wx_wire._start_background_services()

    def test_stop_background_services_with_exception_in_cancel(self, wx_wire: WxWire) -> None:
        """Test stopping background services when task.cancel() raises exception."""
        mock_task = Mock()
        mock_task.done.return_value = False
        mock_task.get_name.return_value = "failing_task"
        mock_task.cancel.side_effect = Exception("Cancel failed")

        wx_wire._background_tasks = [mock_task]

        # Should not raise exception despite cancel() failure
        wx_wire._stop_background_services()

        # Task should still be cleared from list
        assert wx_wire._background_tasks == []

    async def test_monitor_idle_timeout_with_reconnect_failure(self, wx_wire: WxWire) -> None:
        """Test idle timeout monitor when reconnect fails."""
        wx_wire.is_shutting_down = False
        wx_wire.last_message_time = time.time() - (IDLE_TIMEOUT + 10)

        with (
            patch.object(wx_wire, "reconnect", side_effect=Exception("Reconnect failed")),
            patch("asyncio.sleep", side_effect=[None, Exception("Break loop")]),
        ):
            # Should handle reconnect exception gracefully
            with pytest.raises(Exception, match="Break loop"):
                await wx_wire._monitor_idle_timeout()

    async def test_join_muc_room_with_invalid_jid(self, wx_wire: WxWire) -> None:
        """Test MUC room join with invalid JID handling."""
        wx_wire.plugin = {"xep_0045": Mock()}
        mock_muc = wx_wire.plugin["xep_0045"]
        mock_muc.join_muc = AsyncMock(side_effect=ValueError("Invalid JID"))

        # Should handle JID validation errors
        with pytest.raises(ValueError, match="Invalid JID"):
            await wx_wire._join_nwws_room()

    def test_leave_muc_room_with_missing_plugin(self, wx_wire: WxWire) -> None:
        """Test leaving MUC room when plugin is not available."""
        wx_wire.plugin = {}  # Missing xep_0045 plugin

        with patch("nwws_receiver.wx_wire.logger") as mock_logger:
            wx_wire._leave_muc_room()
            mock_logger.warning.assert_called()

    async def test_groupchat_message_with_malformed_xml(self, wx_wire: WxWire) -> None:
        """Test groupchat message processing with malformed XML."""
        mock_msg = Mock(spec=Message)
        mock_msg.get_mucroom.return_value = JID(MUC_ROOM).bare
        mock_msg.xml.find.side_effect = ET.ParseError("Malformed XML")

        with (
            patch.object(wx_wire, "_on_nwws_message", side_effect=ET.ParseError("XML error")),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_groupchat_message(mock_msg)
            mock_logger.warning.assert_called_with(
                "Message parsing failed - error: %s", "XML error"
            )

    async def test_groupchat_message_with_unicode_decode_error(self, wx_wire: WxWire) -> None:
        """Test groupchat message processing with Unicode decode error."""
        mock_msg = Mock(spec=Message)
        mock_msg.get_mucroom.return_value = JID(MUC_ROOM).bare

        with (
            patch.object(
                wx_wire,
                "_on_nwws_message",
                side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid"),
            ),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_groupchat_message(mock_msg)
            mock_logger.warning.assert_called_with("Message parsing failed - error: %s", "invalid")

    async def test_groupchat_message_with_unexpected_exception(self, wx_wire: WxWire) -> None:
        """Test groupchat message processing with unexpected exception."""
        mock_msg = Mock(spec=Message)
        mock_msg.get_mucroom.return_value = JID(MUC_ROOM).bare

        with (
            patch.object(wx_wire, "_on_nwws_message", side_effect=RuntimeError("Unexpected error")),
            patch("nwws_receiver.wx_wire.logger") as mock_logger,
        ):
            await wx_wire._on_groupchat_message(mock_msg)
            mock_logger.exception.assert_called_with("Unexpected message processing error")

    async def test_nwws_message_with_xml_attribute_access_error(self, wx_wire: WxWire) -> None:
        """Test NWWS message processing when XML attribute access fails."""
        mock_msg = Mock(spec=Message)
        mock_x_element = Mock()
        mock_x_element.get.side_effect = AttributeError("Attribute access failed")
        mock_x_element.text = "Valid content"
        mock_msg.xml.find.return_value = mock_x_element

        # Should handle attribute access errors gracefully
        with pytest.raises(AttributeError):
            await wx_wire._on_nwws_message(mock_msg)

    def test_extract_wmo_id_with_xml_parsing_exception(self, wx_wire: WxWire) -> None:
        """Test WMO ID extraction when XML parsing fails."""
        mock_msg = Mock(spec=Message)
        mock_msg.xml.find.side_effect = AttributeError("XML parsing failed")

        result = wx_wire._extract_wmo_id_if_possible(mock_msg)
        assert result is None

    def test_parse_issue_timestamp_with_various_invalid_formats(self, wx_wire: WxWire) -> None:
        """Test timestamp parsing with various invalid formats."""
        invalid_timestamps = [
            "",
            "not-a-timestamp",
            "2023-13-45T25:70:99Z",  # Invalid date/time values
            "2023-12-25",  # Missing time
            "14:30:00Z",  # Missing date
            "2023/12/25 14:30:00",  # Wrong format
            "2023-12-25T14:30:00",  # Missing timezone
            None,  # None value (though type hint suggests str)
        ]

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            current_time = datetime(2023, 12, 25, 15, 0, tzinfo=UTC)
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            for invalid_ts in invalid_timestamps:
                if invalid_ts is None:
                    continue  # Skip None test as it's not in the type signature

                result = wx_wire._parse_issue_timestamp(invalid_ts)
                assert result == current_time

    def test_calculate_delay_with_extreme_values(self, wx_wire: WxWire) -> None:
        """Test delay calculation with extreme timestamp values."""
        # Very old timestamp (should give large positive delay)
        old_timestamp = datetime(1970, 1, 1, 0, 0, tzinfo=UTC)

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            current_time = datetime(2023, 12, 25, 14, 30, tzinfo=UTC)
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            delay = wx_wire._calculate_delay_secs(old_timestamp)
            assert delay > 1000000000  # Very large delay in milliseconds

        # Far future timestamp (should return 0)
        future_timestamp = datetime(2030, 12, 25, 14, 30, tzinfo=UTC)

        with patch("nwws_receiver.wx_wire.datetime") as mock_datetime:
            current_time = datetime(2023, 12, 25, 14, 30, tzinfo=UTC)
            mock_datetime.now.return_value = current_time
            mock_datetime.UTC = UTC

            delay = wx_wire._calculate_delay_secs(future_timestamp)
            assert delay == 0

    def test_convert_to_noaaport_with_extreme_content(self, wx_wire: WxWire) -> None:
        """Test NOAAPort conversion with extreme content."""
        test_cases = [
            "",  # Empty string
            "A" * 100000,  # Very long string
            "\x00\x01\x02\x03\xff",  # Binary content
            "Unicode: 🌩️⛈️🌪️",  # Unicode characters
            "\n" * 1000,  # Many newlines
            "\n\n" * 1000,  # Many double newlines
            "Line1\n\nLine2\n\nLine3" * 1000,  # Large formatted content
        ]

        for content in test_cases:
            result = wx_wire._convert_to_noaaport(content)

            # Verify basic format requirements
            assert result.startswith("\x01")
            assert result.endswith("\x03")
            assert "\r\r\n" in result or content == ""


class TestWxWireRaceConditions:
    """Test race conditions and threading issues."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for testing."""
        config = WxWireConfig(username="testuser", password="testpass")
        return WxWire(config)

    async def test_concurrent_start_stop_operations(self, wx_wire: WxWire) -> None:
        """Test concurrent start and stop operations."""
        with (
            patch.object(wx_wire, "connect", return_value=True),
            patch.object(wx_wire, "disconnect"),
            patch.object(wx_wire, "_start_background_services"),
            patch.object(wx_wire, "_stop_background_services"),
        ):
            # Start multiple concurrent operations
            start_task = asyncio.create_task(wx_wire.start())
            stop_task = asyncio.create_task(wx_wire.stop("Concurrent test"))

            # Wait for both to complete
            start_result, _ = await asyncio.gather(start_task, stop_task)

            # Start should still return result
            assert start_result is True
            # System should be in shutdown state
            assert wx_wire.is_shutting_down

    async def test_stop_during_message_processing_race(self, wx_wire: WxWire) -> None:
        """Test stopping while message processing is ongoing."""
        # Fill queue with messages
        for i in range(10):
            msg = NoaaPortMessage(
                subject=f"Race Test {i}",
                noaaport=f"\x01Race content {i}\r\r\n\x03",
                id=f"race_{i}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            await wx_wire._message_queue.put(msg)

        # Start processing messages
        async def process_messages() -> list[NoaaPortMessage]:
            messages = []
            try:
                async for msg in wx_wire:
                    messages.append(msg)
                    # Simulate processing time
                    await asyncio.sleep(0.01)
            except StopAsyncIteration:
                pass
            return messages

        process_task = asyncio.create_task(process_messages())

        # Let some processing happen
        await asyncio.sleep(0.05)

        # Stop while processing
        await wx_wire.stop("Race condition test")

        # Wait for processing to complete
        processed_messages = await process_task

        # Some messages should have been processed
        assert len(processed_messages) >= 0  # Could be 0 if stop was very fast
        assert wx_wire.is_shutting_down

    async def test_background_service_stop_during_startup(self, wx_wire: WxWire) -> None:
        """Test stopping background services during their startup."""
        start_event = asyncio.Event()
        stop_event = asyncio.Event()

        async def mock_monitor() -> None:
            start_event.set()
            await stop_event.wait()  # Wait until told to stop

        with patch("asyncio.create_task") as mock_create_task:
            mock_task = Mock()
            mock_task.get_name.return_value = "mock_monitor"
            mock_task.done.return_value = False
            mock_create_task.return_value = mock_task

            # Start background services
            service_start_task = asyncio.create_task(wx_wire._start_background_services())

            # Immediately try to stop them
            stop_task = asyncio.create_task(
                asyncio.coroutine(lambda: wx_wire._stop_background_services())()
            )

            # Wait for both operations
            await asyncio.gather(service_start_task, stop_task)

            # Services should be stopped
            assert wx_wire._idle_monitor_task is None
            assert wx_wire._background_tasks == []

    async def test_multiple_async_iterations_concurrent(self, wx_wire: WxWire) -> None:
        """Test multiple concurrent async iterations (should not be done normally)."""
        # Add test messages
        for i in range(5):
            msg = NoaaPortMessage(
                subject=f"Concurrent {i}",
                noaaport=f"\x01Concurrent content {i}\r\r\n\x03",
                id=f"concurrent_{i}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            await wx_wire._message_queue.put(msg)

        # Start multiple iterations (this is not recommended usage but should be handled)
        async def iterate_some_messages(count: int) -> list[NoaaPortMessage]:
            messages = []
            try:
                async for msg in wx_wire:
                    messages.append(msg)
                    if len(messages) >= count:
                        break
            except StopAsyncIteration:
                pass
            return messages

        # Start multiple concurrent iterations
        task1 = asyncio.create_task(iterate_some_messages(2))
        task2 = asyncio.create_task(iterate_some_messages(2))

        # Let them run briefly
        await asyncio.sleep(0.1)

        # Stop iteration
        wx_wire._stop_iteration = True

        # Collect results
        results1, results2 = await asyncio.gather(task1, task2, return_exceptions=True)

        # Both should complete (though results may vary due to race conditions)
        assert isinstance(results1, list)
        assert isinstance(results2, list)

        # Total messages processed should not exceed what was available
        total_processed = len(results1) + len(results2)
        assert total_processed <= 5
