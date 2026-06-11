"""Live verification of the Sarvam pipeline — uses real credits (a few calls).

    set SARVAM_API_KEY=<your key>
    python scripts/sarvam_check.py path\\to\\recording.wav

Runs the WAV through configs/pipeline.sarvam.json (Saarika ASR -> Sarvam
translate -> redact -> delete -> taxonomy signals) and prints the insight,
the detected languages, and exactly how many credits the conversation cost.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.config import load_settings
from voclyp.contracts import ConversationContext, build_insight
from voclyp.languages import load_languages
from voclyp.pipeline.registry import build_pipeline, load_pipeline_config
from voclyp.security import AudioVault
from voclyp.taxonomy import load_taxonomy

if not os.environ.get("SARVAM_API_KEY"):
    sys.exit("set SARVAM_API_KEY first")
if len(sys.argv) < 2:
    sys.exit("usage: python scripts/sarvam_check.py <audio.wav>")

repo = Path(__file__).resolve().parents[1]
config = load_pipeline_config(repo / "configs" / "pipeline.sarvam.json")
services = {
    "vault": AudioVault(),
    "taxonomy": load_taxonomy("fmcg"),
    "settings": load_settings(),
    "languages": load_languages(),
}
ctx = ConversationContext(
    tenant_id="check", conversation_id="sarvam-1", industry="fmcg",
    audio_paths=[sys.argv[1]], consent_captured=True,
)
build_pipeline(config, services).run(ctx)

print("transcript (original -> normalized):")
for utt in ctx.utterances:
    print(f"  [{utt.speaker}] {utt.text}")
    if utt.normalized_text != utt.text:
        print(f"      -> {utt.normalized_text}")
doc = build_insight(ctx)
print("languages:", doc["languages"])
print("signals:", json.dumps(doc["signals"], indent=2, ensure_ascii=False))
print("stage versions:", doc["audit"]["stage_versions"])
print("credits used this conversation:", ctx.provider_usage)
print("audio deleted:", not Path(sys.argv[1]).exists())
