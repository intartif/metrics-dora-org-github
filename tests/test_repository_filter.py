import pytest

from dora_metrics.repository_filter import (
    CustomPropertyFilter,
    NamePatternFilter,
    RepoTypeResolver,
    build_repo_filter_strategy,
)


class FakeGitHubClient:
    def __init__(self, paginated_responses=None, get_responses=None):
        self._paginated_responses = paginated_responses or {}
        self._get_responses = get_responses or {}

    def get(self, path, params=None):
        return self._get_responses[path]

    def get_paginated(self, path, params=None, items_key=None):
        items = self._paginated_responses.get(path, [])
        for item in items:
            yield item


def test_name_pattern_filter_matches_by_regex():
    client = FakeGitHubClient(
        paginated_responses={
            "/orgs/my-org/repos": [
                {"name": "lib-ios-core", "full_name": "my-org/lib-ios-core",
                 "default_branch": "main", "visibility": "private"},
                {"name": "backend-service", "full_name": "my-org/backend-service",
                 "default_branch": "main", "visibility": "private"},
                {"name": "lib-android-core", "full_name": "my-org/lib-android-core",
                 "default_branch": "main", "visibility": "internal"},
            ]
        }
    )
    strategy = NamePatternFilter(client, "my-org", r"^lib-")

    repos = strategy.list_repositories()

    assert {repo.name for repo in repos} == {"lib-ios-core", "lib-android-core"}


def test_name_pattern_filter_invalid_regex_raises():
    client = FakeGitHubClient()
    with pytest.raises(ValueError):
        NamePatternFilter(client, "my-org", r"[unclosed")


def test_name_pattern_filter_resolves_type_from_name_mapping():
    client = FakeGitHubClient(
        paginated_responses={
            "/orgs/my-org/repos": [
                {"name": "lib-ios-core", "full_name": "my-org/lib-ios-core",
                 "default_branch": "main", "visibility": "private"},
            ]
        }
    )
    resolver = RepoTypeResolver(name_to_type_mapping={"lib-ios-core": "ios"})
    strategy = NamePatternFilter(client, "my-org", r"^lib-", type_resolver=resolver)

    repos = strategy.list_repositories()

    assert repos[0].repo_type == "ios"


def test_custom_property_filter_matches_key_value():
    client = FakeGitHubClient(
        paginated_responses={
            "/orgs/my-org/properties/schema": [{"property_name": "platform"}],
            "/orgs/my-org/properties/values": [
                {
                    "repository_name": "lib-ios-core",
                    "properties": [{"property_name": "platform", "value": "ios"}],
                },
                {
                    "repository_name": "backend-service",
                    "properties": [{"property_name": "platform", "value": "backend"}],
                },
            ],
        },
        get_responses={
            "/repos/my-org/lib-ios-core": {
                "full_name": "my-org/lib-ios-core",
                "default_branch": "main",
                "visibility": "private",
            }
        },
    )
    strategy = CustomPropertyFilter(client, "my-org", "platform=ios")

    repos = strategy.list_repositories()

    assert len(repos) == 1
    assert repos[0].name == "lib-ios-core"
    assert repos[0].repo_type == "ios"


def test_custom_property_filter_unknown_property_raises():
    client = FakeGitHubClient(
        paginated_responses={
            "/orgs/my-org/properties/schema": [{"property_name": "platform"}],
        }
    )
    with pytest.raises(ValueError):
        CustomPropertyFilter(client, "my-org", "unknown_key=value").list_repositories()


def test_custom_property_filter_requires_key_value_format():
    client = FakeGitHubClient()
    with pytest.raises(ValueError):
        CustomPropertyFilter(client, "my-org", "no-equals-sign")


def test_build_repo_filter_strategy_factory():
    client = FakeGitHubClient()
    strategy = build_repo_filter_strategy("name_pattern", "^lib-", client, "my-org")
    assert isinstance(strategy, NamePatternFilter)


def test_build_repo_filter_strategy_factory_unknown_type_raises():
    client = FakeGitHubClient()
    with pytest.raises(ValueError):
        build_repo_filter_strategy("unknown", "value", client, "my-org")
