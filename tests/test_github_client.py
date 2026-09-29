import requests

from dora_metrics.github_client import GitHubClient


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._json_data


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self._responses.pop(0)


def test_get_returns_json_body():
    session = FakeSession([FakeResponse(json_data={"login": "my-org"})])
    client = GitHubClient(token="tok", session=session)

    result = client.get("/orgs/my-org")

    assert result == {"login": "my-org"}


def test_get_paginated_follows_link_header():
    session = FakeSession(
        [
            FakeResponse(
                json_data=[{"name": "repo-a"}],
                headers={"Link": '<https://api.github.com/orgs/my-org/repos?page=2>; rel="next"'},
            ),
            FakeResponse(json_data=[{"name": "repo-b"}], headers={}),
        ]
    )
    client = GitHubClient(token="tok", session=session)

    items = list(client.get_paginated("/orgs/my-org/repos"))

    assert [item["name"] for item in items] == ["repo-a", "repo-b"]
    assert len(session.calls) == 2


def test_get_paginated_with_items_key():
    session = FakeSession(
        [FakeResponse(json_data={"workflow_runs": [{"id": 1}, {"id": 2}]}, headers={})]
    )
    client = GitHubClient(token="tok", session=session)

    items = list(client.get_paginated("/repos/o/r/actions/runs", items_key="workflow_runs"))

    assert [item["id"] for item in items] == [1, 2]


def test_rate_limit_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    session = FakeSession(
        [
            FakeResponse(
                status_code=403,
                headers={"X-RateLimit-Remaining": "0", "Retry-After": "1"},
            ),
            FakeResponse(status_code=200, json_data={"ok": True}),
        ]
    )
    client = GitHubClient(token="tok", session=session)

    result = client.get("/orgs/my-org")

    assert result == {"ok": True}
    assert len(session.calls) == 2


def test_server_error_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    session = FakeSession(
        [
            FakeResponse(status_code=503, text="unavailable"),
            FakeResponse(status_code=200, json_data={"ok": True}),
        ]
    )
    client = GitHubClient(token="tok", session=session, max_retries=3)

    result = client.get("/orgs/my-org")

    assert result == {"ok": True}


def test_non_retryable_error_raises(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    session = FakeSession([FakeResponse(status_code=404, text="not found")])
    client = GitHubClient(token="tok", session=session)

    try:
        client.get("/orgs/missing-org")
        assert False, "expected GitHubApiError"
    except Exception as exc:
        assert "404" in str(exc)
