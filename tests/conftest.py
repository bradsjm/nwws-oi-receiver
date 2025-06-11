"""Shared test fixtures and configuration for nwws-receiver tests."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from slixmpp import JID
from slixmpp.stanza import Message

from nwws_receiver.config import WxWireConfig
from nwws_receiver.message import NoaaPortMessage
from nwws_receiver.wx_wire import MUC_ROOM


@pytest.fixture
def event_loop() -> asyncio.AbstractEventLoop:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def wx_wire_config() -> WxWireConfig:
    """Create a standard test configuration for WxWire."""
    return WxWireConfig(
        username="testuser",
        password="testpass",
        server="test.nwws.example.com",
        port=5222,
        history=10,
    )


@pytest.fixture
def minimal_wx_wire_config() -> WxWireConfig:
    """Create a minimal test configuration for WxWire."""
    return WxWireConfig(
        username="testuser",
        password="testpass",
    )


@pytest.fixture
def sample_noaaport_message() -> NoaaPortMessage:
    """Create a sample NoaaPortMessage for testing."""
    return NoaaPortMessage(
        subject="Test Weather Alert",
        noaaport="\x01This is test weather content\r\r\n\x03",
        id="test_message_12345",
        issue=datetime(2023, 12, 25, 14, 30, tzinfo=UTC),
        ttaaii="NOUS41",
        cccc="KOKX",
        awipsid="TESTMSG",
        delay_stamp=None,
    )


@pytest.fixture
def sample_delayed_noaaport_message() -> NoaaPortMessage:
    """Create a sample NoaaPortMessage with delay stamp for testing."""
    return NoaaPortMessage(
        subject="Delayed Weather Alert",
        noaaport="\x01This is delayed weather content\r\r\n\x03",
        id="delayed_message_67890",
        issue=datetime(2023, 12, 25, 14, 30, tzinfo=UTC),
        ttaaii="WFUS51",
        cccc="KBOS",
        awipsid="DELAYTEST",
        delay_stamp=datetime(2023, 12, 25, 14, 25, tzinfo=UTC),
    )


@pytest.fixture
def mock_xmpp_message() -> Message:
    """Create a mock XMPP message with realistic NWWS-OI content."""
    msg = Mock(spec=Message)
    msg.get_mucroom.return_value = JID(MUC_ROOM).bare
    msg.get_id.return_value = "xmpp_msg_12345"
    msg.get.side_effect = lambda key, default="": {
        "body": "URGENT - WEATHER MESSAGE",
        "subject": "National Weather Service Alert",
    }.get(key, default)

    # Create mock XML with NWWS-OI namespace
    mock_xml = Mock()
    mock_x_element = Mock()
    mock_x_element.get.side_effect = lambda key, default="": {
        "id": "nws_product_56789",
        "issue": "2023-12-25T15:45:00Z",
        "ttaaii": "WFUS51",
        "cccc": "KBOS",
        "awipsid": "SVRBOS",
    }.get(key, default)
    mock_x_element.text = (
        "URGENT - WEATHER MESSAGE\n"
        "NATIONAL WEATHER SERVICE BOSTON MA\n\n"
        "SEVERE THUNDERSTORM WARNING FOR...\n"
        "MIDDLESEX COUNTY IN EASTERN MASSACHUSETTS...\n\n"
        "AT 345 PM EST...A SEVERE THUNDERSTORM WAS LOCATED NEAR FRAMINGHAM..."
    )

    mock_xml.find.return_value = mock_x_element
    msg.xml = mock_xml

    # Mock delay handling - no delay by default
    msg.__contains__ = lambda self, key: False
    msg.__getitem__ = lambda self, key: None

    return msg


@pytest.fixture
def mock_xmpp_message_with_delay() -> Message:
    """Create a mock XMPP message with delay stamp."""
    msg = Mock(spec=Message)
    msg.get_mucroom.return_value = JID(MUC_ROOM).bare
    msg.get_id.return_value = "delayed_xmpp_msg"
    msg.get.side_effect = lambda key, default="": {
        "body": "DELAYED - WEATHER MESSAGE",
        "subject": "Delayed Weather Alert",
    }.get(key, default)

    # Create mock XML with NWWS-OI namespace
    mock_xml = Mock()
    mock_x_element = Mock()
    mock_x_element.get.side_effect = lambda key, default="": {
        "id": "delayed_product_99999",
        "issue": "2023-12-25T15:30:00Z",
        "ttaaii": "NOUS41",
        "cccc": "KOKX",
        "awipsid": "DELAYOKX",
    }.get(key, default)
    mock_x_element.text = "This message was delayed in transmission."

    mock_xml.find.return_value = mock_x_element
    msg.xml = mock_xml

    # Mock delay handling - with 5 minute delay
    msg.__contains__ = lambda self, key: key == "delay"
    msg.__getitem__ = (
        lambda self, key: {"stamp": datetime(2023, 12, 25, 15, 25, tzinfo=UTC)}
        if key == "delay"
        else None
    )

    return msg


@pytest.fixture
def mock_invalid_xmpp_message() -> Message:
    """Create a mock XMPP message without NWWS-OI namespace."""
    msg = Mock(spec=Message)
    msg.get_mucroom.return_value = JID(MUC_ROOM).bare
    msg.get_id.return_value = "invalid_msg"
    msg.get.side_effect = lambda key, default="": default

    # Mock XML without NWWS-OI namespace
    mock_xml = Mock()
    mock_xml.find.return_value = None  # No NWWS-OI element found
    msg.xml = mock_xml

    msg.__contains__ = lambda self, key: False
    msg.__getitem__ = lambda self, key: None

    return msg


@pytest.fixture
def mock_empty_body_xmpp_message() -> Message:
    """Create a mock XMPP message with NWWS-OI namespace but empty body."""
    msg = Mock(spec=Message)
    msg.get_mucroom.return_value = JID(MUC_ROOM).bare
    msg.get_id.return_value = "empty_body_msg"
    msg.get.side_effect = lambda key, default="": default

    # Create mock XML with NWWS-OI namespace but empty text
    mock_xml = Mock()
    mock_x_element = Mock()
    mock_x_element.get.side_effect = lambda key, default="": {
        "id": "empty_product",
        "issue": "2023-12-25T16:00:00Z",
        "ttaaii": "NOUS41",
        "cccc": "KOKX",
        "awipsid": "EMPTY",
    }.get(key, default)
    mock_x_element.text = ""  # Empty body

    mock_xml.find.return_value = mock_x_element
    msg.xml = mock_xml

    msg.__contains__ = lambda self, key: False
    msg.__getitem__ = lambda self, key: None

    return msg


@pytest.fixture
def wrong_room_xmpp_message() -> Message:
    """Create a mock XMPP message from wrong MUC room."""
    msg = Mock(spec=Message)
    msg.get_mucroom.return_value = "wrong@room.example.com"
    msg.__getitem__ = Mock(return_value=Mock(bare="wrong@room.example.com"))

    return msg


@pytest.fixture
def sample_weather_products() -> list[str]:
    """Provide sample weather product content for testing."""
    return [
        # Severe Weather Warning
        "URGENT - WEATHER MESSAGE\n"
        "NATIONAL WEATHER SERVICE BOSTON MA\n\n"
        "SEVERE THUNDERSTORM WARNING FOR...\n"
        "MIDDLESEX COUNTY IN EASTERN MASSACHUSETTS...\n\n"
        "AT 445 PM EST...A SEVERE THUNDERSTORM WAS LOCATED NEAR FRAMINGHAM...",
        # Forecast Discussion
        "AREA FORECAST DISCUSSION\n"
        "NATIONAL WEATHER SERVICE BOSTON MA\n\n"
        "SYNOPSIS...\n"
        "A COLD FRONT WILL MOVE THROUGH THE REGION THIS EVENING...\n\n"
        "NEAR TERM /THROUGH TONIGHT/...\n"
        "EXPECT SCATTERED SHOWERS AND THUNDERSTORMS...",
        # Public Forecast
        "PUBLIC FORECAST PRODUCTS\n"
        "NATIONAL WEATHER SERVICE BOSTON MA\n\n"
        "TODAY...PARTLY CLOUDY WITH A CHANCE OF SHOWERS.\n"
        "HIGHS IN THE UPPER 70S. SOUTHWEST WINDS 10 TO 15 MPH.\n\n"
        "TONIGHT...MOSTLY CLOUDY WITH SCATTERED SHOWERS.\n"
        "LOWS IN THE MID 60S.",
    ]


@pytest.fixture
def sample_wmo_headers() -> list[dict[str, str]]:
    """Provide sample WMO header combinations for testing."""
    return [
        {
            "ttaaii": "WFUS51",
            "cccc": "KBOS",
            "awipsid": "SVRBOS",
            "description": "Severe Weather Statement - Boston",
        },
        {
            "ttaaii": "FXUS61",
            "cccc": "KBOS",
            "awipsid": "AFDBOS",
            "description": "Area Forecast Discussion - Boston",
        },
        {
            "ttaaii": "FPUS51",
            "cccc": "KOKX",
            "awipsid": "FPUOKX",
            "description": "Public Forecast - New York",
        },
        {
            "ttaaii": "NOUS41",
            "cccc": "KOKX",
            "awipsid": "PNSOKX",
            "description": "Public Information Statement - New York",
        },
        {
            "ttaaii": "WWUS51",
            "cccc": "KMHX",
            "awipsid": "WWSMHX",
            "description": "Storm Warning - Morehead City",
        },
    ]


@pytest.fixture
def sample_timestamps() -> list[str]:
    """Provide sample timestamp formats for testing."""
    return [
        "2023-12-25T14:30:00Z",  # Standard ISO format with Z
        "2023-12-25T14:30:00+00:00",  # ISO format with timezone
        "2023-12-25T14:30:00.123Z",  # With milliseconds
        "2023-12-25T14:30:00.123456Z",  # With microseconds
        "invalid-timestamp",  # Invalid format
        "",  # Empty string
        "2023-13-32T25:70:70Z",  # Invalid date/time values
    ]


# Performance testing helpers
@pytest.fixture
def large_message_queue_size() -> int:
    """Provide a large queue size for performance testing."""
    return 1000


@pytest.fixture
def stress_test_message_count() -> int:
    """Provide message count for stress testing."""
    return 100


# Test markers for different test categories
pytest_plugins = ["pytest_asyncio"]

# Configure asyncio test mode
pytestmark = pytest.mark.asyncio
