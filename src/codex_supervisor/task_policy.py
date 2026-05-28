"""Shared task-boundary policy for supervisor-owned and worker-owned files."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from fnmatch import fnmatchcase
from typing import Any

from codex_supervisor.execution_surface import canonical_worker_backend

CONTROLLER_TASK_ROLES = frozenset({"controller", "planning", "promotion", "source_lock"})
CONTROLLER_MUTATION_KINDS = CONTROLLER_TASK_ROLES

PROTECTED_SOURCE_OF_TRUTH_DOCUMENTS = frozenset(
    {
        ".gitignore",
        ".gitattributes",
        "README.md",
        "AGENTS.md",
        "PLANS.md",
        "ARCHITECTURE.md",
        "CONTRACTS.md",
        "ROADMAP.md",
        "SOP.md",
        "TESTING.md",
        "DECISIONS.md",
        "LICENSE",
        "ATTRIBUTIONS.md",
    }
)

CONTROLLER_OWNED_EXACT_PATHS = frozenset(
    {
        "plans/planning.sqlite3",
        "HANDOFF.md",
        "scripts/check_file_justification.py",
        "scripts/check_planning_integrity.py",
        "scripts/check_protected_files.py",
        "scripts/print_protected_hashes.py",
        "scripts/verify.py",
    }
)

CONTROLLER_OWNED_GLOB_PATHS = frozenset(
    {
        ".agents/**",
        "artifacts/**",
        "plans/**",
        "runs/**",
        "worktrees/**",
    }
)


def task_allows_controller_owned_paths(
    scope: object,
    *,
    worker_backend: str = "codex_exec",
) -> bool:
    """Return whether a worker task is explicitly a controller-state task.

    Broad booleans and legacy role labels such as ``controller_task`` are intentionally not enough.
    They caused product workers to receive supervisor-owned files as normal implementation scope.
    A task must declare a typed ``controller_mutation_kind`` value.
    """

    if canonical_worker_backend(worker_backend) != "codex_exec":
        return True
    parsed_scope = _json_object(scope)
    if _declares_product_surface(parsed_scope):
        return False
    return _controller_mutation_kind(parsed_scope) in CONTROLLER_MUTATION_KINDS


def controller_owned_allowed_path_violations(
    allowed_paths: Iterable[object],
    *,
    scope: object,
    worker_backend: str = "codex_exec",
) -> tuple[str, ...]:
    """Return policy violations for codex_exec allowed paths."""

    normalized_paths = tuple(_normalize_path(value) for value in allowed_paths)
    normalized_paths = tuple(path for path in normalized_paths if path)
    violations: list[str] = []
    parsed_scope = _json_object(scope)
    legacy_controller_role = _legacy_controller_role(parsed_scope)
    controller_mutation_kind = _controller_mutation_kind(parsed_scope)

    for path, forbidden in _worker_must_not_edit_overlaps(normalized_paths, scope):
        violations.append(f"{path}: allowed path overlaps worker_must_not_edit `{forbidden}`")

    if controller_mutation_kind is not None and _declares_product_surface(parsed_scope):
        violations.append(
            f"controller_mutation_kind={controller_mutation_kind}: "
            "product_surface tasks cannot use controller worker profile"
        )

    if task_allows_controller_owned_paths(scope, worker_backend=worker_backend):
        return tuple(dict.fromkeys(violations))

    for path in normalized_paths:
        reason = controller_owned_path_reason(path)
        if reason is not None:
            if legacy_controller_role is not None:
                violations.append(
                    f"{legacy_controller_role}: legacy controller role is ignored without "
                    "controller_mutation_kind"
                )
            violations.append(f"{path}: {reason}")
    return tuple(dict.fromkeys(violations))


def task_uses_controller_worker_profile(scope: object) -> bool:
    """Return whether a task should receive the controller-worker profile."""

    parsed_scope = _json_object(scope)
    return (
        not _declares_product_surface(parsed_scope)
        and _controller_mutation_kind(parsed_scope) in CONTROLLER_MUTATION_KINDS
    )


def controller_owned_path_reason(path: object) -> str | None:
    """Return why a path is supervisor-owned, or ``None`` when worker-owned."""

    normalized = _normalize_path(path)
    if not normalized:
        return None
    if normalized in CONTROLLER_OWNED_EXACT_PATHS:
        return "controller-owned path"
    if normalized in PROTECTED_SOURCE_OF_TRUTH_DOCUMENTS:
        return "protected source-of-truth doc"
    if normalized == "scripts/**":
        return "controller-owned path"
    for pattern in CONTROLLER_OWNED_GLOB_PATHS:
        if _patterns_may_overlap(normalized, pattern):
            return "controller-owned path"
    return None


def _worker_must_not_edit_overlaps(
    allowed_paths: Iterable[str],
    scope: object,
) -> tuple[tuple[str, str], ...]:
    parsed_scope = _json_object(scope)
    forbidden_paths = _json_string_array(parsed_scope.get("worker_must_not_edit"))
    overlaps: list[tuple[str, str]] = []
    for allowed in allowed_paths:
        for forbidden in forbidden_paths:
            if _patterns_may_overlap(allowed, forbidden):
                overlaps.append((allowed, forbidden))
    return tuple(overlaps)


def _controller_mutation_kind(scope: Mapping[str, Any]) -> str | None:
    value = scope.get("controller_mutation_kind")
    return value if isinstance(value, str) and value in CONTROLLER_MUTATION_KINDS else None


def _declares_product_surface(scope: Mapping[str, Any]) -> bool:
    value = scope.get("product_surface")
    return isinstance(value, str) and bool(value.strip())


def _legacy_controller_role(scope: Mapping[str, Any]) -> str | None:
    if scope.get("controller_task") is True:
        return "controller_task"
    role = scope.get("task_role", scope.get("worker_role"))
    if role in CONTROLLER_TASK_ROLES:
        return f"task_role={role}" if scope.get("task_role") == role else f"worker_role={role}"
    return None


def _json_object(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return parsed
    return {}


def _json_string_array(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        normalized
        for item in value
        if isinstance(item, str)
        for normalized in (_normalize_path(item),)
        if normalized
    )


def _normalize_path(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().replace("\\", "/").lstrip("./")


def _patterns_may_overlap(left: str, right: str) -> bool:
    if left == right:
        return True
    left_prefix = _glob_prefix(left)
    right_prefix = _glob_prefix(right)
    if left.endswith("/**") and right_prefix.startswith(left_prefix):
        return True
    if right.endswith("/**") and left_prefix.startswith(right_prefix):
        return True
    return fnmatchcase(left, right) or fnmatchcase(right, left)


def _glob_prefix(pattern: str) -> str:
    if pattern.endswith("/**"):
        return pattern[:-3]
    wildcard_positions = (pattern.find("*"), pattern.find("?"), pattern.find("["))
    wildcard_index = min(
        (index for index in wildcard_positions if index >= 0),
        default=-1,
    )
    if wildcard_index < 0:
        return pattern
    return pattern[:wildcard_index].rstrip("/")
