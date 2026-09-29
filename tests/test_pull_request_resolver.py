from dora_metrics.pull_request_resolver import PullRequestResolver


class FakeGitHubClient:
    def __init__(self, pulls_by_key):
        self._pulls_by_key = pulls_by_key
        self.calls = []

    def get(self, path, params=None):
        raise NotImplementedError

    def get_paginated(self, path, params=None, items_key=None):
        self.calls.append(path)
        for key, pulls in self._pulls_by_key.items():
            if path.endswith(key):
                for pull in pulls:
                    yield pull
                return
        return


def test_resolve_for_sha_returns_none_without_sha():
    client = FakeGitHubClient({})
    resolver = PullRequestResolver(client, "my-org")

    assert resolver.resolve_for_sha("lib-ios-core", "") is None


def test_resolve_for_sha_returns_none_when_no_pulls():
    client = FakeGitHubClient({"/commits/abc123/pulls": []})
    resolver = PullRequestResolver(client, "my-org")

    assert resolver.resolve_for_sha("lib-ios-core", "abc123") is None


def test_resolve_for_sha_prefers_merged_pull_request():
    client = FakeGitHubClient(
        {
            "/commits/abc123/pulls": [
                {"number": 1, "title": "Open PR", "html_url": "url1", "updated_at": "2024-03-20T00:00:00Z"},
                {"number": 2, "title": "Merged PR", "html_url": "url2", "merged_at": "2024-03-17T08:00:00Z"},
            ]
        }
    )
    resolver = PullRequestResolver(client, "my-org")

    result = resolver.resolve_for_sha("lib-ios-core", "abc123")

    assert result.number == 2
    assert result.title == "Merged PR"
    assert result.merged_at is not None


def test_resolve_for_sha_falls_back_to_most_recently_updated_when_none_merged():
    client = FakeGitHubClient(
        {
            "/commits/abc123/pulls": [
                {"number": 1, "title": "Old PR", "html_url": "url1", "updated_at": "2024-03-10T00:00:00Z"},
                {"number": 2, "title": "Newer PR", "html_url": "url2", "updated_at": "2024-03-20T00:00:00Z"},
            ]
        }
    )
    resolver = PullRequestResolver(client, "my-org")

    result = resolver.resolve_for_sha("lib-ios-core", "abc123")

    assert result.number == 2
    assert result.merged_at is None


def test_resolve_for_sha_caches_results_per_repo_and_sha():
    client = FakeGitHubClient(
        {"/commits/abc123/pulls": [{"number": 1, "title": "PR", "html_url": "url1", "merged_at": "2024-03-17T08:00:00Z"}]}
    )
    resolver = PullRequestResolver(client, "my-org")

    first = resolver.resolve_for_sha("lib-ios-core", "abc123")
    second = resolver.resolve_for_sha("lib-ios-core", "abc123")

    assert first == second
    assert len(client.calls) == 1
