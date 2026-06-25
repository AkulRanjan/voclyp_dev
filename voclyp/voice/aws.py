"""AWS-backed speaker embedding (optional, for production accuracy).

Selected with VOCLYP_VOICEPRINT_BACKEND=aws. Delegates voiceprint generation to
a SageMaker real-time endpoint hosting a speaker-embedding model (e.g.
pyannote / SpeechBrain ECAPA-TDNN), invoked via boto3. The endpoint is expected
to take raw audio bytes and return a JSON list of floats (the embedding).

This keeps the platform's contract intact: it returns the same
``{'vector', 'model', 'frames'}`` shape as the dependency-free baseline, so the
enrollment endpoint and the speaker_id pipeline stage are unchanged. If boto3 or
the endpoint are not configured, the caller (voclyp.voice.fingerprint.embed)
catches the error and falls back to the acoustic baseline.

Credentials come from the task's IAM role in AWS (preferred) or AWS_* env vars
locally — never hard-coded. Uses the $10k AWS credits via SageMaker hosting.
"""
from __future__ import annotations

import json
import math
import os

MODEL_AWS = "aws-sagemaker-speaker-embedding"


def _l2_normalize(vec):
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def aws_embed(audio: bytes) -> dict:
    endpoint = os.environ.get("VOCLYP_VOICEPRINT_SAGEMAKER_ENDPOINT")
    if not endpoint:
        raise RuntimeError("VOCLYP_VOICEPRINT_SAGEMAKER_ENDPOINT not set")
    import boto3  # optional dependency; only needed for the aws backend

    client = boto3.client("sagemaker-runtime",
                          region_name=os.environ.get("AWS_REGION"))
    resp = client.invoke_endpoint(
        EndpointName=endpoint,
        ContentType="application/octet-stream",
        Body=audio,
    )
    payload = json.loads(resp["Body"].read())
    vector = payload["embedding"] if isinstance(payload, dict) else payload
    return {"vector": _l2_normalize([float(x) for x in vector]),
            "model": MODEL_AWS, "frames": 0}
