"""Performance and stress tests for wx_wire.py module."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from slixmpp import JID
from slixmpp.stanza import Message

from nwws_receiver.config import WxWireConfig
from nwws_receiver.message import NoaaPortMessage
from nwws_receiver.wx_wire import MUC_ROOM, WxWire


class TestWxWirePerformance:
    """Performance tests for WxWire functionality."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for performance testing."""
        config = WxWireConfig(
            username="perftest",
            password="testpass",
            server="perf.test.com",
            port=5222,
            history=5,
        )
        return WxWire(config)

    @pytest.mark.slow
    async def test_high_volume_message_processing(self, wx_wire: WxWire) -> None:
        """Test processing high volume of messages efficiently."""
        message_count = 1000
        start_time = time.monotonic()

        # Create test messages
        test_messages = []
        for i in range(message_count):
            msg = NoaaPortMessage(
                subject=f"High Volume Message {i}",
                noaaport=f"\x01Content for message {i}\r\r\n\x03",
                id=f"perf_test_{i:06d}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
                awipsid=f"PERF{i:03d}",
            )
            test_messages.append(msg)

        # Queue all messages
        for msg in test_messages:
            await wx_wire._message_queue.put(msg)

        # Process all messages
        processed_messages = []
        for _ in range(message_count):
            processed_msg = await wx_wire._message_queue.get()
            processed_messages.append(processed_msg)

        end_time = time.monotonic()
        processing_time = end_time - start_time

        # Performance assertions
        assert len(processed_messages) == message_count
        assert processing_time < 10.0  # Should complete within 10 seconds
        messages_per_second = message_count / processing_time
        assert messages_per_second > 100  # Should process >100 messages/second

        # Verify message integrity
        for i, msg in enumerate(processed_messages):
            assert msg.subject == f"High Volume Message {i}"
            assert msg.id == f"perf_test_{i:06d}"

    @pytest.mark.slow
    async def test_concurrent_message_processing(self, wx_wire: WxWire) -> None:
        """Test concurrent message processing with multiple producers."""
        messages_per_producer = 100
        producer_count = 5
        total_messages = messages_per_producer * producer_count

        async def message_producer(producer_id: int) -> None:
            """Produce messages concurrently."""
            for i in range(messages_per_producer):
                msg = NoaaPortMessage(
                    subject=f"Producer {producer_id} Message {i}",
                    noaaport=f"\x01Producer {producer_id} content {i}\r\r\n\x03",
                    id=f"producer_{producer_id}_{i:03d}",
                    issue=datetime.now(UTC),
                    ttaaii="NOUS41",
                    cccc="KOKX",
                    awipsid=f"P{producer_id}M{i:02d}",
                )
                await wx_wire._message_queue.put(msg)

        # Start concurrent producers
        start_time = time.monotonic()
        producer_tasks = [
            asyncio.create_task(message_producer(i), name=f"producer_{i}")
            for i in range(producer_count)
        ]

        # Consume messages concurrently
        consumer_task = asyncio.create_task(
            self._consume_messages(wx_wire, total_messages),
            name="consumer",
        )

        # Wait for all tasks to complete
        await asyncio.gather(*producer_tasks, consumer_task)
        end_time = time.monotonic()

        processing_time = end_time - start_time
        messages_per_second = total_messages / processing_time

        # Performance assertions
        assert processing_time < 15.0  # Should complete within 15 seconds
        assert messages_per_second > 50  # Should maintain reasonable throughput

    async def _consume_messages(self, wx_wire: WxWire, count: int) -> list[NoaaPortMessage]:
        """Helper to consume messages from queue."""
        messages = []
        for _ in range(count):
            msg = await wx_wire._message_queue.get()
            messages.append(msg)
        return messages

    @pytest.mark.slow
    async def test_queue_backpressure_performance(self, wx_wire: WxWire) -> None:
        """Test queue backpressure handling under load."""
        queue_size = wx_wire._message_queue.maxsize
        overflow_count = 50

        # Fill queue to capacity
        for i in range(queue_size):
            msg = NoaaPortMessage(
                subject=f"Queue Fill {i}",
                noaaport=f"\x01Queue content {i}\r\r\n\x03",
                id=f"queue_{i:03d}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            await wx_wire._message_queue.put(msg)

        assert wx_wire.queue_size == queue_size

        # Attempt to add overflow messages (should fail quickly)
        overflow_start = time.monotonic()
        overflow_failures = 0

        for i in range(overflow_count):
            msg = NoaaPortMessage(
                subject=f"Overflow {i}",
                noaaport=f"\x01Overflow content {i}\r\r\n\x03",
                id=f"overflow_{i:03d}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            try:
                wx_wire._message_queue.put_nowait(msg)
            except asyncio.QueueFull:
                overflow_failures += 1

        overflow_time = time.monotonic() - overflow_start

        # Performance assertions
        assert overflow_failures == overflow_count  # All should fail
        assert overflow_time < 1.0  # Should fail quickly
        assert wx_wire.queue_size == queue_size  # Queue still at capacity

    async def test_message_conversion_performance(self, wx_wire: WxWire) -> None:
        """Test NOAAPort message conversion performance."""
        test_texts = [
            "Short message",
            "Medium length message with\n\nmultiple lines\n\nand formatting",
            "Long message " * 100 + "\n\n" + "with multiple paragraphs " * 50,
            "Very long message " * 1000 + "\n\n" * 100 + "extensive content " * 200,
        ]

        conversion_times = []

        for text in test_texts:
            start_time = time.monotonic()

            # Convert multiple times to get average
            for _ in range(100):
                result = wx_wire._convert_to_noaaport(text)

            end_time = time.monotonic()
            avg_time = (end_time - start_time) / 100
            conversion_times.append(avg_time)

            # Verify conversion correctness
            assert result.startswith("\x01")
            assert result.endswith("\x03")
            assert "\r\r\n" in result

        # Performance assertions
        max_conversion_time = max(conversion_times)
        assert max_conversion_time < 0.001  # Should convert in <1ms on average

    async def test_timestamp_parsing_performance(self, wx_wire: WxWire) -> None:
        """Test timestamp parsing performance with various formats."""
        timestamps = [
            "2023-12-25T14:30:00Z",
            "2023-12-25T14:30:00.123Z",
            "2023-12-25T14:30:00.123456Z",
            "2023-12-25T14:30:00+00:00",
            "invalid-timestamp",  # Should fallback to current time
        ]

        parsing_times = []

        for timestamp in timestamps:
            start_time = time.monotonic()

            # Parse multiple times to get average
            for _ in range(1000):
                result = wx_wire._parse_issue_timestamp(timestamp)

            end_time = time.monotonic()
            avg_time = (end_time - start_time) / 1000
            parsing_times.append(avg_time)

            # Verify result is valid datetime
            assert isinstance(result, datetime)
            assert result.tzinfo is not None

        # Performance assertions
        max_parsing_time = max(parsing_times)
        assert max_parsing_time < 0.0001  # Should parse in <0.1ms on average

    @pytest.mark.slow
    async def test_background_service_overhead(self, wx_wire: WxWire) -> None:
        """Test overhead of background services during message processing."""
        message_count = 500

        # Mock the background services to avoid actual network operations
        with (
            patch.object(wx_wire, "_monitor_idle_timeout", new_callable=AsyncMock) as mock_monitor,
            patch("asyncio.create_task") as mock_create_task,
        ):
            # Setup mock task
            mock_task = Mock()
            mock_task.get_name.return_value = "mock_monitor"
            mock_create_task.return_value = mock_task

            # Start background services
            await wx_wire._start_background_services()

            # Process messages while services are running
            start_time = time.monotonic()

            for i in range(message_count):
                msg = NoaaPortMessage(
                    subject=f"Background Test {i}",
                    noaaport=f"\x01Background content {i}\r\r\n\x03",
                    id=f"bg_test_{i:03d}",
                    issue=datetime.now(UTC),
                    ttaaii="NOUS41",
                    cccc="KOKX",
                )
                await wx_wire._message_queue.put(msg)

            # Consume all messages
            for _ in range(message_count):
                await wx_wire._message_queue.get()

            end_time = time.monotonic()
            processing_time = end_time - start_time

            # Stop background services
            wx_wire._stop_background_services()

            # Performance assertions
            messages_per_second = message_count / processing_time
            assert messages_per_second > 100  # Should maintain throughput with services running
            assert mock_create_task.called  # Background services should have started


class TestWxWireStressTests:
    """Stress tests for WxWire under extreme conditions."""

    @pytest.fixture
    def wx_wire(self) -> WxWire:
        """Create WxWire instance for stress testing."""
        config = WxWireConfig()
        return WxWire(config)

    @pytest.mark.slow
    async def test_rapid_connect_disconnect_cycles(self, wx_wire: WxWire) -> None:
        """Test rapid connection/disconnection cycles."""
        cycle_count = 20

        with (
            patch.object(wx_wire, "connect", return_value=True) as mock_connect,
            patch.object(wx_wire, "disconnect") as mock_disconnect,
            patch.object(wx_wire, "_start_background_services") as mock_start_services,
            patch.object(wx_wire, "_stop_background_services") as mock_stop_services,
        ):
            start_time = time.monotonic()

            for cycle in range(cycle_count):
                # Start connection
                result = await wx_wire.start()
                assert result is True

                # Simulate brief operation
                await asyncio.sleep(0.01)

                # Stop connection
                await wx_wire.stop(f"Cycle {cycle}")

                # Reset shutdown flag for next cycle
                wx_wire.is_shutting_down = False
                wx_wire._stop_iteration = False

            end_time = time.monotonic()
            cycle_time = end_time - start_time

            # Stress test assertions
            assert cycle_time < 5.0  # Should complete all cycles quickly
            assert mock_connect.call_count == cycle_count
            assert mock_disconnect.call_count == cycle_count

    @pytest.mark.slow
    async def test_memory_usage_under_load(self, wx_wire: WxWire) -> None:
        """Test memory usage doesn't grow excessively under load."""
        import gc

        # Force garbage collection before test
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Process many messages
        message_count = 1000
        batch_size = 100

        for batch in range(message_count // batch_size):
            # Create and process batch of messages
            for i in range(batch_size):
                msg_id = batch * batch_size + i
                msg = NoaaPortMessage(
                    subject=f"Memory Test {msg_id}",
                    noaaport=f"\x01Memory test content {msg_id}\r\r\n\x03",
                    id=f"mem_test_{msg_id:06d}",
                    issue=datetime.now(UTC),
                    ttaaii="NOUS41",
                    cccc="KOKX",
                )
                await wx_wire._message_queue.put(msg)

            # Consume batch
            for _ in range(batch_size):
                await wx_wire._message_queue.get()

            # Force garbage collection periodically
            if batch % 5 == 0:
                gc.collect()

        # Final garbage collection
        gc.collect()
        final_objects = len(gc.get_objects())

        # Memory usage should not grow significantly
        object_growth = final_objects - initial_objects
        assert object_growth < 1000, f"Excessive object growth: {object_growth}"

    @pytest.mark.slow
    async def test_error_recovery_under_stress(self, wx_wire: WxWire) -> None:
        """Test error recovery capabilities under stress conditions."""
        error_count = 0
        success_count = 0
        total_operations = 200

        # Mock XMPP message processing with random failures
        async def mock_process_with_errors(msg: Message) -> NoaaPortMessage | None:
            nonlocal error_count, success_count

            # Simulate random processing errors (20% failure rate)
            if error_count < total_operations * 0.2 and (error_count + success_count) % 5 == 0:
                error_count += 1
                raise Exception(f"Simulated processing error {error_count}")

            success_count += 1
            return NoaaPortMessage(
                subject="Stress Test Message",
                noaaport="\x01Stress test content\r\r\n\x03",
                id=f"stress_{success_count}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )

        # Create mock messages
        mock_messages = []
        for i in range(total_operations):
            msg = Mock(spec=Message)
            msg.get_mucroom.return_value = JID(MUC_ROOM).bare
            msg.get_id.return_value = f"stress_msg_{i}"
            mock_messages.append(msg)

        # Process all messages with error handling
        processed_count = 0
        error_count = 0

        with patch.object(wx_wire, "_on_nwws_message", side_effect=mock_process_with_errors):
            for msg in mock_messages:
                try:
                    await wx_wire._on_groupchat_message(msg)
                    processed_count += 1
                except Exception:
                    error_count += 1
                    # System should continue processing despite errors

        # Stress test assertions
        assert processed_count > 0  # Some messages should be processed successfully
        assert error_count > 0  # Some errors should occur (by design)
        assert processed_count + error_count == total_operations

    async def test_shutdown_during_high_load(self, wx_wire: WxWire) -> None:
        """Test graceful shutdown during high message load."""
        message_count = 500

        # Fill queue with messages
        for i in range(message_count):
            msg = NoaaPortMessage(
                subject=f"Shutdown Test {i}",
                noaaport=f"\x01Shutdown test content {i}\r\r\n\x03",
                id=f"shutdown_{i:03d}",
                issue=datetime.now(UTC),
                ttaaii="NOUS41",
                cccc="KOKX",
            )
            await wx_wire._message_queue.put(msg)

        assert wx_wire.queue_size == message_count

        # Start async iteration
        iteration_task = asyncio.create_task(
            self._iterate_messages(wx_wire, message_count // 2),
            name="message_iterator",
        )

        # Let some messages process
        await asyncio.sleep(0.1)

        # Initiate shutdown while processing
        shutdown_start = time.monotonic()
        await wx_wire.stop("High load shutdown test")
        shutdown_time = time.monotonic() - shutdown_start

        # Wait for iteration to complete
        with pytest.raises(StopAsyncIteration):
            await iteration_task

        # Shutdown should be quick even under load
        assert shutdown_time < 2.0
        assert wx_wire.is_shutting_down
        assert wx_wire._stop_iteration

    async def _iterate_messages(self, wx_wire: WxWire, count: int) -> None:
        """Helper to iterate through messages."""
        processed = 0
        async for message in wx_wire:
            processed += 1
            if processed >= count:
                break
