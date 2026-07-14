"""Data core: the CallEvent and its persistence.

This package knows nothing about the gateway or any provider: it only defines the data
contract and how it is stored. Its only outward dependency is `pricing`.
"""

from llmobs.recording.event import SCHEMA_VERSION, CallEvent, new_event
from llmobs.recording.recorder import Recorder
from llmobs.recording.store import EventStore

__all__ = ["SCHEMA_VERSION", "CallEvent", "new_event", "Recorder", "EventStore"]
