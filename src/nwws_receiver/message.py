"""NOAAPort Message Data Model."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NoaaPortMessage:
    """Represents a structured weather message received from the NWWS-OI system.

    This data model encapsulates all the essential metadata and content of a weather
    product message received through the NWWS-OI XMPP Multi-User Chat (MUC) room.
    The message includes standardized weather product identifiers (WMO headers),
    timing information, issuing office details, and the formatted product content
    in NOAAPort format for downstream processing.

    The message structure follows the NWWS-OI XML namespace format with additional
    processing to convert the raw message content into the NOAAPort format expected
    by weather data consumers. Delay stamps are preserved to track message latency
    through the distribution system.

    Attributes:
        subject: Subject of the message.
        noaaport: NOAAPort formatted text of the product message.
        id: Unique identifier for the product (server process ID and sequence number).
        issue: Issue time of the product as a datetime object.
        ttaaii: TTAAII code representing the WMO product type and time.
        cccc: CCCC code representing the issuing office or center.
        awipsid: AWIPS ID (AFOS PIL) of the product if available.
        delay_stamp: Delay stamp if the message was delayed, otherwise None.

    """

    subject: str
    noaaport: str
    id: str
    issue: datetime
    ttaaii: str
    cccc: str
    awipsid: str = "NONE"
    delay_stamp: datetime | None = None
