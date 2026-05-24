from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROUTER_SKILL_BODY = (
    "---\n"
    "name: skill-router\n"
    "description: Route useful skills during tests.\n"
    "---\n"
    "\n"
    "## Route By Intent\n"
    "\n"
    "- Demo: `demo`.\n"
)


def test_skill_inventory_accepts_routed_skill(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        ROUTER_SKILL_BODY,
    )
    _write_skill(tmp_path, "codex-supervisor", description="Top-level orchestrator for tests.")

    failures = module.check_skill_inventory(tmp_path)

    assert failures == ()


def test_skill_inventory_rejects_name_mismatch_and_unrouted_skill(tmp_path):
    module = _load_skill_inventory_module()
    _write(
        tmp_path / ".agents" / "skills" / "demo" / "SKILL.md",
        "---\nname: other\ndescription: A useful demo skill for tests.\n---\n",
    )

    failures = module.check_skill_inventory(tmp_path)

    assert any("does not match folder" in failure.reason for failure in failures)
    assert any("not explicitly routed" in failure.reason for failure in failures)


def test_skill_inventory_rejects_incidental_route_mentions(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        (
            "---\nname: skill-router\ndescription: Route useful skills during tests.\n---\n"
            "\n## Route By Intent\n\n"
            "Mention `demo` in prose without routing it.\n"
        ),
    )
    _write_skill(tmp_path, "codex-supervisor", description="Top-level orchestrator for tests.")

    failures = module.check_skill_inventory(tmp_path)

    assert any("not explicitly routed" in failure.reason for failure in failures)


def test_skill_inventory_rejects_incidental_bullet_route_mentions(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        (
            "---\nname: skill-router\ndescription: Route useful skills during tests.\n---\n"
            "\n## Route By Intent\n\n"
            "- Mention `demo` in a bullet without routing syntax.\n"
        ),
    )
    _write_skill(tmp_path, "codex-supervisor", description="Top-level orchestrator for tests.")

    failures = module.check_skill_inventory(tmp_path)

    assert any("not explicitly routed" in failure.reason for failure in failures)


def test_skill_inventory_ignores_codex_supervisor_route_mentions(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        (
            "---\nname: skill-router\ndescription: Route useful skills during tests.\n---\n"
            "\n## Route By Intent\n\n"
            "- Other: `other`.\n"
        ),
    )
    _write(
        tmp_path / ".agents" / "skills" / "codex-supervisor" / "SKILL.md",
        (
            "---\nname: codex-supervisor\ndescription: Top-level orchestrator for tests.\n---\n"
            "- Demo: `demo`.\n"
        ),
    )

    failures = module.check_skill_inventory(tmp_path)

    assert any("not explicitly routed by skill-router" in failure.reason for failure in failures)


def test_skill_inventory_ignores_incidental_colon_bullet_outside_route_section(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        (
            "---\nname: skill-router\ndescription: Route useful skills during tests.\n---\n"
            "\n## Notes\n\n"
            "- Note: mention `demo` while explaining something else.\n"
        ),
    )
    _write_skill(tmp_path, "codex-supervisor", description="Top-level orchestrator for tests.")

    failures = module.check_skill_inventory(tmp_path)

    assert any("not explicitly routed by skill-router" in failure.reason for failure in failures)


def test_skill_inventory_requires_route_map_files(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")

    failures = module.check_skill_inventory(tmp_path)

    assert any("route map file is missing" in failure.reason for failure in failures)


def test_skill_inventory_rejects_prohibited_skill_text(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(
        tmp_path,
        "demo",
        description="A useful routed demo skill for tests.",
        body="Do this with Claude Code.",
    )
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        ROUTER_SKILL_BODY,
    )

    failures = module.check_skill_inventory(tmp_path)

    assert any("prohibited reference" in failure.reason for failure in failures)


def test_skill_inventory_rejects_prohibited_skill_text_case_insensitively(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(
        tmp_path,
        "demo",
        description="A useful routed demo skill for tests.",
        body="Do this with claude code.",
    )
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        ROUTER_SKILL_BODY,
    )

    failures = module.check_skill_inventory(tmp_path)

    assert any("prohibited reference" in failure.reason for failure in failures)


def test_skill_inventory_rejects_prohibited_support_file_text(tmp_path):
    module = _load_skill_inventory_module()
    _write_skill(tmp_path, "demo", description="A useful routed demo skill for tests.")
    _write(
        tmp_path / ".agents" / "skills" / "demo" / "REFERENCE.md",
        "Do this with Claude Code.",
    )
    _write(
        tmp_path / ".agents" / "skills" / "skill-router" / "SKILL.md",
        ROUTER_SKILL_BODY,
    )

    failures = module.check_skill_inventory(tmp_path)

    assert any(
        failure.relative_path.endswith("REFERENCE.md") and "prohibited reference" in failure.reason
        for failure in failures
    )


def _load_skill_inventory_module() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "check_skill_inventory.py"
    spec = importlib.util.spec_from_file_location("check_skill_inventory", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_skill(
    repo_root: Path,
    name: str,
    *,
    description: str,
    body: str = "Use this skill in tests.",
) -> None:
    _write(
        repo_root / ".agents" / "skills" / name / "SKILL.md",
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
