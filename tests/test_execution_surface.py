from codex_supervisor.execution_surface import (
    CODEX_REASONING_EFFORT_CONFIG_KEY,
    codex_exec_capability_mappings,
    goal_mode_decision,
    worker_backend_execution_surface,
)


def test_codex_exec_execution_surface_is_live_backend():
    surface = worker_backend_execution_surface("codex_exec")

    assert surface.as_json() == {
        "name": "codex_exec",
        "backend_status": "available",
        "execution_mode": "codex_exec",
        "native_goal_support": "prompt_rendered_fallback_only",
        "official_noninteractive_native_goal_path": False,
    }


def test_unknown_execution_surface_requires_backend_specific_preflight():
    surface = worker_backend_execution_surface("manual")

    assert surface.as_json() == {
        "name": "manual",
        "backend_status": "backend_specific_preflight_required",
        "execution_mode": "use_backend_only_after_preflight",
        "native_goal_support": "backend_specific_preflight_required",
        "official_noninteractive_native_goal_path": False,
    }


def test_codex_exec_capability_mappings_name_reasoning_effort_transport():
    mappings = codex_exec_capability_mappings(model="gpt-test", reasoning_effort="high")

    assert mappings["reasoning_effort"] == {
        "requested": "high",
        "transport": "config_override",
        "codex_config_key": CODEX_REASONING_EFFORT_CONFIG_KEY,
        "fallback": "retry_without_reasoning_effort_when_cli_rejects_mapping",
    }
    assert mappings["model"] == {
        "requested": "gpt-test",
        "transport": "cli_model_flag",
        "fallback": "retry_with_cli_default_when_account_rejects_model_before_work",
    }


def test_goal_mode_decision_names_prompt_rendered_fallback():
    assert goal_mode_decision(native_goal_mode=False) == "prompt_rendered_fallback"
    assert (
        goal_mode_decision(native_goal_mode=True)
        == "native_goal_requested_but_prompt_rendered_fallback"
    )
