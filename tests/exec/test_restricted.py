"""Restricted-token sandbox (Feature 4): limits and readiness, unit-tested."""
from squad.exec.windows.restricted import (
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOB_OBJECT_LIMIT_PROCESS_MEMORY,
    JOB_OBJECT_LIMIT_JOB_TIME,
    RestrictedLaunchPlan,
    level3_ready,
    plan_launch,
    restricted_marker_path,
    restricted_token_attributes,
)


def test_plan_always_enforces_kill_on_close_and_process_count():
    plan = plan_launch(memory_limit_mb=512, max_processes=8, time_limit_seconds=120)
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_ACTIVE_PROCESS


def test_plan_applies_memory_and_time_limits():
    plan = plan_launch(memory_limit_mb=512, max_processes=8, time_limit_seconds=120)
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_JOB_TIME
    assert plan.process_memory_limit_bytes == 512 * 1024 * 1024


def test_plan_zero_memory_disables_only_memory_limit():
    plan = plan_launch(memory_limit_mb=0)
    assert not (plan.job_limit_flags & JOB_OBJECT_LIMIT_PROCESS_MEMORY)
    # kill-on-close and process cap are never disabled
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert plan.job_limit_flags & JOB_OBJECT_LIMIT_ACTIVE_PROCESS


def test_token_attributes_restrict_and_low_integrity():
    plan = plan_launch(low_integrity=True)
    attrs = restricted_token_attributes(plan)
    assert attrs["disable_max_privilege"] is True
    assert attrs["sanitize_ids"] is True
    assert attrs["low_integrity_sid"] == "S-1-16-4096"


def test_appcontainer_no_network_flag():
    plan = plan_launch(app_container=True, network_off=True)
    attrs = restricted_token_attributes(plan)
    assert attrs["app_container_no_network"] is True
    off = plan_launch(app_container=True, network_off=False)
    assert restricted_token_attributes(off)["app_container_no_network"] is False


def test_level3_readiness_requires_verified_marker(tmp_path):
    marker = tmp_path / "squad" / "level3.json"
    assert level3_ready(marker) is False          # missing
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("unverified", encoding="utf-8")
    assert level3_ready(marker) is False          # present but not verified
    marker.write_text("verified", encoding="utf-8")
    assert level3_ready(marker) is True           # verified


def test_marker_path_lives_under_squad_dir():
    p = restricted_marker_path(r"C:\Users\x\AppData\Local")
    assert "squad" in p.parts and p.name == "level3.json"


def test_adapter_level3_distinct_from_level2():
    assert JOB_OBJECT_LIMIT_PROCESS_MEMORY != JOB_OBJECT_LIMIT_JOB_TIME
    p = RestrictedLaunchPlan(512, 8, 120)
    assert p.app_container is False  # default: restricted-token path, not AppContainer
