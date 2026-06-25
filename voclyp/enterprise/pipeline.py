"""Assemble the enterprise pipeline from settings.

``build_enterprise(settings)`` wires the store, event bus, S3 audio store,
consent service, ingestion, the three workers (Sarvam ASR, Bedrock extractor,
routing dispatcher), and the erasure worker. Each external client is created
only when its credentials are present; otherwise the offline mock is used.

With the in-memory bus (offline/dev), worker handlers are subscribed so a
single ``ingest`` cascades the whole pipeline synchronously. With Kafka, the
workers run as independent consumer processes (see runner entrypoints) and the
subscriptions here are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass

from .asr.sarvam_worker import SarvamAsrWorker
from .config import EnterpriseSettings, load_enterprise_settings
from .consent.service import ConsentService
from .erasure.worker import ErasureWorker
from .events import topics
from .events.bus import InMemoryBus, open_event_bus
from .extraction.bedrock_worker import BedrockExtractor
from .ingestion import EnterpriseIngestion
from .routing.dispatcher import RoutingDispatcher
from .routing.push import PushClient
from .routing.twilio_whatsapp import TwilioWhatsAppClient
from .routing.zoho import ZohoClient
from .storage.s3 import open_audio_store
from .store import open_store


@dataclass
class EnterprisePipeline:
    settings: EnterpriseSettings
    store: object
    bus: object
    audio_store: object
    consent: ConsentService
    ingestion: EnterpriseIngestion
    asr: SarvamAsrWorker
    extractor: BedrockExtractor
    dispatcher: RoutingDispatcher
    erasure: ErasureWorker


def _build_sarvam_client(settings):
    if not settings.sarvam_api_key:
        return None, None
    try:
        from ..providers.sarvam import SarvamClient
    except Exception:
        return None, None
    client = SarvamClient(settings.sarvam_api_key)

    def batch_factory(mode):  # pragma: no cover - needs sarvamai + key
        from sarvamai import SarvamAI

        sdk = SarvamAI(api_subscription_key=settings.sarvam_api_key)
        return sdk.speech_to_text_job.create_job(
            model="saaras:v3", mode=mode, language_code="unknown",
            with_diarization=True, num_speakers=2)

    return client, batch_factory


def _build_bedrock_client(settings):
    if not settings.has_bedrock():
        return None
    try:  # pragma: no cover - needs boto3 + AWS
        import boto3

        kwargs = {"region_name": settings.aws_region}
        if settings._aws_creds_present():
            kwargs.update(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key)
            if settings.aws_session_token:
                kwargs["aws_session_token"] = settings.aws_session_token
        return boto3.client("bedrock-runtime", **kwargs)
    except Exception:
        return None


def build_enterprise(settings: EnterpriseSettings | None = None,
                     dispatch: bool = True) -> EnterprisePipeline:
    settings = settings or load_enterprise_settings()

    store = open_store(settings)
    bus = open_event_bus(settings, dispatch=dispatch)
    audio_store = open_audio_store(settings)

    consent = ConsentService(store)
    ingestion = EnterpriseIngestion(settings, store, audio_store, bus, consent)

    sarvam_client, batch_factory = _build_sarvam_client(settings)
    asr = SarvamAsrWorker(settings, store, bus, audio_store,
                          client=sarvam_client, batch_factory=batch_factory)

    extractor = BedrockExtractor(settings, store, bus,
                                 client=_build_bedrock_client(settings))

    clients = {
        "zoho": ZohoClient(settings, live=settings.has_zoho()),
        "whatsapp": TwilioWhatsAppClient(settings, live=settings.has_twilio()),
        "push": PushClient(settings),
    }
    dispatcher = RoutingDispatcher(settings, store, clients, bus=bus)

    erasure = ErasureWorker(settings, store, audio_store)

    # Synchronous in-process cascade only makes sense for the in-memory bus.
    if isinstance(bus, InMemoryBus):
        bus.subscribe(topics.AUDIO_RAW_UPLOADED, asr.handle)
        bus.subscribe(topics.TRANSCRIPT_READY, extractor.handle)
        bus.subscribe(topics.INSIGHT_EXTRACTED, dispatcher.handle)

    return EnterprisePipeline(
        settings=settings, store=store, bus=bus, audio_store=audio_store,
        consent=consent, ingestion=ingestion, asr=asr, extractor=extractor,
        dispatcher=dispatcher, erasure=erasure)
