from datetime import date, datetime, timedelta, timezone

import pytest

from dora_metrics.config import (
    ConfigValidationError,
    DateRangeError,
    RepoFilterType,
    build_date_range,
    load_run_config_from_env,
    parse_repo_filter_type,
    validate_repo_filter_value,
)

TODAY = date(2024, 3, 31)


def test_build_date_range_valid_week():
    date_range = build_date_range("2024-03-18", today=TODAY)
    assert date_range.start == date(2024, 3, 18)
    assert date_range.end == date(2024, 3, 24)


def test_build_date_range_invalid_format_raises():
    with pytest.raises(ConfigValidationError):
        build_date_range("18-03-2024", today=TODAY)


def test_build_date_range_end_after_today_raises():
    with pytest.raises(DateRangeError):
        build_date_range("2024-03-30", today=TODAY)


def test_build_date_range_older_than_30_days_raises():
    with pytest.raises(DateRangeError):
        build_date_range("2024-02-01", today=TODAY)


def test_build_date_range_exactly_30_days_boundary_is_valid():
    date_range = build_date_range("2024-03-01", today=TODAY)
    assert date_range.start == date(2024, 3, 1)
    assert date_range.end == date(2024, 3, 7)


def test_build_date_range_today_as_end_is_valid():
    date_range = build_date_range("2024-03-25", today=TODAY)
    assert date_range.end == TODAY


def test_parse_repo_filter_type_valid():
    assert parse_repo_filter_type("name_pattern") is RepoFilterType.NAME_PATTERN
    assert parse_repo_filter_type("custom_property") is RepoFilterType.CUSTOM_PROPERTY


def test_parse_repo_filter_type_invalid_raises():
    with pytest.raises(ConfigValidationError):
        parse_repo_filter_type("invalid_type")


def test_validate_repo_filter_value_requires_key_value_for_custom_property():
    with pytest.raises(ConfigValidationError):
        validate_repo_filter_value(RepoFilterType.CUSTOM_PROPERTY, "platform")


def test_validate_repo_filter_value_accepts_key_value_for_custom_property():
    value = validate_repo_filter_value(RepoFilterType.CUSTOM_PROPERTY, "platform=ios")
    assert value == "platform=ios"


def test_validate_repo_filter_value_rejects_empty():
    with pytest.raises(ConfigValidationError):
        validate_repo_filter_value(RepoFilterType.NAME_PATTERN, "   ")


def test_load_run_config_from_env_success():
    recent_start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    env = {
        "GH_ORG": "my-org",
        "GH_TOKEN": "token-123",
        "REPO_FILTER_TYPE": "name_pattern",
        "REPO_FILTER_VALUE": "^lib-",
        "WEEK_START_DATE": recent_start,
        "TRIGGERED_BY": "jdoe",
    }
    config = load_run_config_from_env(env)
    assert config.org == "my-org"
    assert config.github_token == "token-123"
    assert config.repo_filter_type is RepoFilterType.NAME_PATTERN
    assert config.date_range.start_iso == recent_start


def test_load_run_config_from_env_missing_org_raises():
    recent_start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    env = {
        "GH_TOKEN": "token-123",
        "REPO_FILTER_TYPE": "name_pattern",
        "REPO_FILTER_VALUE": "^lib-",
        "WEEK_START_DATE": recent_start,
    }
    with pytest.raises(ConfigValidationError):
        load_run_config_from_env(env)


def test_load_run_config_from_env_missing_token_raises():
    recent_start = (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()
    env = {
        "GH_ORG": "my-org",
        "REPO_FILTER_TYPE": "name_pattern",
        "REPO_FILTER_VALUE": "^lib-",
        "WEEK_START_DATE": recent_start,
    }
    with pytest.raises(ConfigValidationError):
        load_run_config_from_env(env)
