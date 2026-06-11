"""The stage contract that makes every pipeline component swappable.

A stage takes the ConversationContext, transforms it, and declares a name and
version. The runner records each stage's version into the context so every
insight document carries the exact lineage that produced it, and times each
stage so MLOps monitoring sees latency per component.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from ..contracts import ConversationContext


class Stage(ABC):
    name: str = "stage"
    version: str = "0.0"

    @abstractmethod
    def run(self, ctx: ConversationContext) -> None:
        ...


class PipelineRunner:
    def __init__(self, stages: list):
        self.stages = stages

    def run(self, ctx: ConversationContext) -> ConversationContext:
        for stage in self.stages:
            started = time.perf_counter()
            stage.run(ctx)
            ctx.stage_timings_ms[stage.name] = round(
                (time.perf_counter() - started) * 1000, 2
            )
            ctx.stage_versions[stage.name] = stage.version
        return ctx
