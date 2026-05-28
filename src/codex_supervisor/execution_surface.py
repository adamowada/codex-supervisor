"""Execution-surface vocabulary shared by Goal Contracts and worker backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]

CODEX_EXEC_BACKEND = "codex_exec"
CODEX_EXEC_BACKEND_ALIASES = frozenset({CODEX_EXEC_BACKEND, "live_codex_exec"})
CODEX_REVIEW_BACKEND = "codex_review"
MANUAL_BACKEND = "manual"
SUPPORTED_LIVE_STORY_LOOP_BACKENDS = frozenset({CODEX_EXEC_BACKEND, CODEX_REVIEW_BACKEND})
CODEX_EXEC_BACKEND_STATUS = "available"
CODEX_EXEC_EXECUTION_MODE = CODEX_EXEC_BACKEND
CODEX_EXEC_NATIVE_GOAL_SUPPORT = "prompt_rendered_fallback_only"
CODEX_REASONING_EFFORT_CONFIG_KEY = "model_reasoning_effort"
CODEX_REASONING_EFFORT_FALLBACK = "retry_without_reasoning_effort_when_cli_rejects_mapping"
CODEX_MODEL_FALLBACK = "retry_with_cli_default_when_account_rejects_model_before_work"
NATIVE_GOAL_PROMPT_FALLBACK_DECISION = "prompt_rendered_fallback"
NATIVE_GOAL_REQUESTED_PROMPT_FALLBACK_DECISION = (
    "native_goal_requested_but_prompt_rendered_fallback"
)


@dataclass(frozen=True)
class WorkerBackendExecutionSurface:
    """Human- and worker-facing status for one worker backend."""

    name: str
    backend_status: str
    execution_mode: str
    native_goal_support: str
    official_noninteractive_native_goal_path: bool

    def as_json(self) -> JsonObject:
        return {
            "name": self.name,
            "backend_status": self.backend_status,
            "execution_mode": self.execution_mode,
            "native_goal_support": self.native_goal_support,
            "official_noninteractive_native_goal_path": (
                self.official_noninteractive_native_goal_path
            ),
        }


CODEX_EXEC_SURFACE = WorkerBackendExecutionSurface(
    name=CODEX_EXEC_BACKEND,
    backend_status=CODEX_EXEC_BACKEND_STATUS,
    execution_mode=CODEX_EXEC_EXECUTION_MODE,
    native_goal_support=CODEX_EXEC_NATIVE_GOAL_SUPPORT,
    official_noninteractive_native_goal_path=False,
)


def worker_backend_execution_surface(worker_backend: str) -> WorkerBackendExecutionSurface:
    canonical_backend = canonical_worker_backend(worker_backend)
    if canonical_backend == CODEX_EXEC_BACKEND:
        return CODEX_EXEC_SURFACE
    return WorkerBackendExecutionSurface(
        name=canonical_backend,
        backend_status="backend_specific_preflight_required",
        execution_mode="use_backend_only_after_preflight",
        native_goal_support="backend_specific_preflight_required",
        official_noninteractive_native_goal_path=False,
    )


def canonical_worker_backend(worker_backend: str) -> str:
    normalized = worker_backend.strip()
    if normalized in CODEX_EXEC_BACKEND_ALIASES:
        return CODEX_EXEC_BACKEND
    return normalized


def is_codex_exec_backend(worker_backend: str) -> bool:
    return canonical_worker_backend(worker_backend) == CODEX_EXEC_BACKEND


def goal_mode_decision(*, native_goal_mode: bool) -> str:
    if native_goal_mode:
        return NATIVE_GOAL_REQUESTED_PROMPT_FALLBACK_DECISION
    return NATIVE_GOAL_PROMPT_FALLBACK_DECISION


def codex_exec_capability_mappings(
    *,
    model: str | None,
    reasoning_effort: str | None,
) -> JsonObject:
    mappings: JsonObject = {}
    if reasoning_effort is not None:
        mappings["reasoning_effort"] = reasoning_effort_capability_mapping(reasoning_effort)
    if model is not None:
        mappings["model"] = {
            "requested": model,
            "transport": "cli_model_flag",
            "fallback": CODEX_MODEL_FALLBACK,
        }
    return mappings


def reasoning_effort_capability_mapping(reasoning_effort: str) -> JsonObject:
    return {
        "requested": reasoning_effort,
        "transport": "config_override",
        "codex_config_key": CODEX_REASONING_EFFORT_CONFIG_KEY,
        "fallback": CODEX_REASONING_EFFORT_FALLBACK,
    }
