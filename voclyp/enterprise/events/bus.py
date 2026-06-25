"""Event bus abstraction.

``InMemoryBus`` (default offline) dispatches synchronously to in-process
subscribers, so a single ``produce`` can cascade the whole pipeline
(ingest -> ASR -> extract -> route) inside one process or test. It also keeps a
log of everything produced for assertions.

``KafkaBus`` publishes/consumes JSON over Apache Kafka (AWS MSK / Confluent /
local redpanda). Each worker runs its own consumer group via ``consume``.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from ...contracts import utcnow


def _make_event(topic: str, value: dict, key: str = "") -> dict:
    return {
        "event_id": uuid.uuid4().hex,
        "topic": topic,
        "key": key,
        "occurred_at": utcnow(),
        "value": value,
    }


class EventBus:
    """Interface marker. Subclasses implement produce/subscribe/consume."""

    def produce(self, topic: str, value: dict, key: str = "") -> dict:
        raise NotImplementedError

    def subscribe(self, topic: str, handler) -> None:
        raise NotImplementedError


class InMemoryBus(EventBus):
    backend = "memory"

    def __init__(self, dispatch: bool = True):
        # dispatch=True invokes subscribers synchronously on produce()
        self.dispatch = dispatch
        self._subs: dict[str, list] = {}
        self.log: list[dict] = []
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler) -> None:
        self._subs.setdefault(topic, []).append(handler)

    def produce(self, topic: str, value: dict, key: str = "") -> dict:
        event = _make_event(topic, value, key)
        with self._lock:
            self.log.append(event)
        if self.dispatch:
            for handler in list(self._subs.get(topic, [])):
                handler(event)
        return event

    # test/inspection helpers ------------------------------------------------
    def events_for(self, topic: str) -> list[dict]:
        return [e for e in self.log if e["topic"] == topic]

    def last(self, topic: str) -> dict | None:
        events = self.events_for(topic)
        return events[-1] if events else None


class KafkaBus(EventBus):  # pragma: no cover - requires a live broker
    backend = "kafka"

    def __init__(self, settings):
        from confluent_kafka import Producer

        self.settings = settings
        self._conf = self._base_conf(settings)
        self._producer = Producer(self._conf)
        self._closed = False

    @staticmethod
    def _base_conf(settings) -> dict:
        conf = {"bootstrap.servers": settings.kafka_bootstrap}
        if settings.kafka_sasl_username:
            conf.update({
                "security.protocol": settings.kafka_security_protocol,
                "sasl.mechanisms": settings.kafka_sasl_mechanism,
                "sasl.username": settings.kafka_sasl_username,
                "sasl.password": settings.kafka_sasl_password,
            })
        return conf

    def produce(self, topic: str, value: dict, key: str = "") -> dict:
        event = _make_event(topic, value, key)
        self._producer.produce(
            topic, key=(key or event["event_id"]).encode("utf-8"),
            value=json.dumps(event).encode("utf-8"),
        )
        self._producer.poll(0)
        return event

    def subscribe(self, topic: str, handler) -> None:
        # Kafka subscription is realized by a dedicated consume() loop, not by
        # in-process registration; kept for interface parity.
        raise NotImplementedError(
            "KafkaBus: run a worker via consume(topics, handler)")

    def consume(self, topics: list[str], handler, group_id: str | None = None,
                stop=None) -> None:
        from confluent_kafka import Consumer

        conf = dict(self._conf)
        conf.update({
            "group.id": group_id or self.settings.kafka_group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        consumer = Consumer(conf)
        consumer.subscribe(list(topics))
        try:
            while not (stop and stop()):
                msg = consumer.poll(1.0)
                if msg is None or msg.error():
                    continue
                event = json.loads(msg.value().decode("utf-8"))
                handler(event)
                consumer.commit(msg)
        finally:
            consumer.close()

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)


def open_event_bus(settings, dispatch: bool = True) -> EventBus:
    """Kafka when configured + importable, else an in-process bus."""
    if settings.has_kafka():
        try:
            return KafkaBus(settings)
        except Exception:
            pass
    return InMemoryBus(dispatch=dispatch)
