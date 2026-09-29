import pytest

from dora_metrics.deploy_classifier import DeployClassifier, DeployMappingError


@pytest.fixture
def classifier():
    mapping = {
        "ios": ["release-ios.yml", "Release iOS"],
        "android": ["release-android.yml"],
        "react": ["publish-artifactory.yml"],
        "monorepo": ["release-ios.yml", "release-android.yml"],
        "default": [],
    }
    return DeployClassifier(mapping)


def test_is_deploy_workflow_matches_by_path_basename(classifier):
    assert classifier.is_deploy_workflow("ios", "CI", ".github/workflows/release-ios.yml")


def test_is_deploy_workflow_matches_by_name(classifier):
    assert classifier.is_deploy_workflow("ios", "Release iOS", "workflow.yml")


def test_is_deploy_workflow_no_match_returns_false(classifier):
    assert not classifier.is_deploy_workflow("ios", "Run Tests", "test.yml")


def test_is_deploy_workflow_wrong_repo_type_returns_false(classifier):
    assert not classifier.is_deploy_workflow("android", "Release iOS", "release-ios.yml")


def test_is_deploy_workflow_monorepo_matches_both_platforms(classifier):
    assert classifier.is_deploy_workflow("monorepo", "CI", "release-android.yml")
    assert classifier.is_deploy_workflow("monorepo", "CI", "release-ios.yml")


def test_is_deploy_workflow_unknown_repo_type_returns_false(classifier):
    assert not classifier.is_deploy_workflow("unknown", "Release iOS", "release-ios.yml")


def test_from_file_missing_file_raises(tmp_path):
    missing_file = tmp_path / "missing.yml"
    with pytest.raises(DeployMappingError):
        DeployClassifier.from_file(missing_file)


def test_from_file_loads_yaml_mapping(tmp_path):
    config_file = tmp_path / "mapping.yml"
    config_file.write_text(
        "react:\n  deploy_workflows:\n    - publish-artifactory.yml\n",
        encoding="utf-8",
    )
    loaded = DeployClassifier.from_file(config_file)
    assert loaded.is_deploy_workflow("react", "CI", "publish-artifactory.yml")


def test_from_file_loads_json_mapping(tmp_path):
    config_file = tmp_path / "mapping.json"
    config_file.write_text(
        '{"react": {"deploy_workflows": ["publish-artifactory.yml"]}}', encoding="utf-8"
    )
    loaded = DeployClassifier.from_file(config_file)
    assert loaded.is_deploy_workflow("react", "CI", "publish-artifactory.yml")
