"""MLOps evaluation harness: every change is measured, not guessed.

Runs labeled conversations (evals/<industry>.json) through the configured
pipeline and scores extracted signals against expected (type, subtype) labels
— precision / recall / F1, per signal type and overall. The report carries the
exact stage and taxonomy versions evaluated, so a regression is attributable
to a specific component change.

CLI (regression gate — nonzero exit below threshold, wired into CI):

    python -m voclyp.mlops.eval --industry fmcg --min-f1 0.8
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from ..contracts import ConversationContext
from ..pipeline.registry import build_pipeline, load_pipeline_config
from ..security import AudioVault
from ..taxonomy import load_taxonomy

DEFAULT_EVAL_DIR = Path(__file__).resolve().parents[2] / "evals"


def _score(expected: set, extracted: set) -> dict:
    tp = len(expected & extracted)
    fp = len(extracted - expected)
    fn = len(expected - extracted)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(precision, 3),
            "recall": round(recall, 3), "f1": round(f1, 3)}


def run_eval(industry: str, eval_dir=None, pipeline_config=None,
             taxonomy_dir=None) -> dict:
    eval_dir = Path(eval_dir or DEFAULT_EVAL_DIR)
    cases = json.loads((eval_dir / f"{industry}.json").read_text(encoding="utf-8"))
    config = pipeline_config or load_pipeline_config()
    vault = AudioVault()
    services = {"vault": vault, "taxonomy": load_taxonomy(industry, taxonomy_dir)}
    pipeline = build_pipeline(config, services)

    all_expected, all_extracted = set(), set()
    case_results = []
    stage_versions = {}
    work_dir = Path(tempfile.mkdtemp(prefix="voclyp-eval-"))
    for case in cases:
        path = work_dir / f"{case['id']}.audio"
        vault.write(path, case["transcript"].encode("utf-8"))
        ctx = ConversationContext(
            tenant_id="eval", conversation_id=case["id"], industry=industry,
            audio_paths=[str(path)], consent_captured=True,
        )
        pipeline.run(ctx)
        stage_versions = ctx.stage_versions

        expected = {(case["id"], s["type"], s["subtype"])
                    for s in case["expected_signals"]}
        extracted = {(case["id"], s.type, s.subtype) for s in ctx.signals}
        all_expected |= expected
        all_extracted |= extracted
        case_results.append({
            "id": case["id"], "language": case.get("language", "?"),
            **_score(expected, extracted),
        })

    by_type = {}
    types = {t for (_, t, _) in all_expected | all_extracted}
    for sig_type in sorted(types):
        by_type[sig_type] = _score(
            {x for x in all_expected if x[1] == sig_type},
            {x for x in all_extracted if x[1] == sig_type},
        )

    return {
        "industry": industry,
        "cases": case_results,
        "by_signal_type": by_type,
        "overall": _score(all_expected, all_extracted),
        "stage_versions": stage_versions,
        "taxonomy_version": services["taxonomy"]["version"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="VoClyp eval harness")
    parser.add_argument("--industry", default="fmcg")
    parser.add_argument("--min-f1", type=float, default=0.8,
                        help="regression gate: fail below this overall F1")
    parser.add_argument("--json", action="store_true", help="emit full JSON report")
    args = parser.parse_args(argv)

    report = run_eval(args.industry)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"eval: {args.industry} | taxonomy {report['taxonomy_version']}")
        for sig_type, score in report["by_signal_type"].items():
            print(f"  {sig_type:<22} P={score['precision']:.2f} "
                  f"R={score['recall']:.2f} F1={score['f1']:.2f}")
        overall = report["overall"]
        print(f"  {'OVERALL':<22} P={overall['precision']:.2f} "
              f"R={overall['recall']:.2f} F1={overall['f1']:.2f}")

    if report["overall"]["f1"] < args.min_f1:
        print(f"FAIL: overall F1 {report['overall']['f1']} < {args.min_f1}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
