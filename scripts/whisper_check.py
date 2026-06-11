"""Manual verification: real spoken audio through the real ASR.

Proves the swappability claim: the only difference from production stub mode
is the pipeline config's asr impl. Generate a WAV (e.g. Windows TTS), then:

    python scripts/whisper_check.py %TEMP%\\voclyp_real.wav
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.contracts import ConversationContext, build_insight
from voclyp.pipeline.registry import build_pipeline, load_pipeline_config
from voclyp.security import AudioVault
from voclyp.taxonomy import load_taxonomy

wav = sys.argv[1]
config = load_pipeline_config()
for spec in config["stages"]:
    if spec["role"] == "asr":
        spec["impl"] = "whisper"          # the entire "model upgrade"
        spec["options"] = {"model_size": "tiny"}

vault = AudioVault()  # plaintext for this check; the wav is synthetic
ctx = ConversationContext(
    tenant_id="check", conversation_id="whisper-1", industry="fmcg",
    audio_paths=[wav], consent_captured=True,
)
pipeline = build_pipeline(config, {"vault": vault, "taxonomy": load_taxonomy("fmcg")})
pipeline.run(ctx)

print("transcript:")
for utt in ctx.utterances:
    print(f"  [{utt.speaker}] {utt.text}")
doc = build_insight(ctx)
print("signals:", json.dumps(doc["signals"], indent=2))
print("asr version:", doc["audit"]["stage_versions"]["asr"])
print("audio deleted at:", doc["audit"]["audio_deleted_at"])
print("wav still exists:", Path(wav).exists())
