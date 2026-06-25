"""Event backbone: Kafka in production, in-process bus offline."""
from __future__ import annotations

from . import topics
from .bus import EventBus, InMemoryBus, KafkaBus, open_event_bus

__all__ = ["EventBus", "InMemoryBus", "KafkaBus", "open_event_bus", "topics"]
