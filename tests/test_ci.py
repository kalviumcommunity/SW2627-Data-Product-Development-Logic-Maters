"""Tests for the GitHub Actions CI workflow (static structure checks only)."""

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"


def _text() -> str:
    assert WORKFLOW.is_file(), f"CI workflow missing: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_exists_and_triggers() -> None:
    text = _text()
    assert "on:" in text
    assert "push" in text
    assert "pull_request" in text


def test_workflow_installs_and_runs_tests() -> None:
    text = _text()
    assert "requirements.txt" in text
    assert "pytest" in text
    assert "setup-python" in text


def test_workflow_runs_smoke_test_without_secrets() -> None:
    text = _text()
    assert "run_pipeline" in text
    assert "showcase" in text
    for secret_token in ("REPORT_SMTP_PASSWORD", "EMAIL_PASSWORD", "secrets."):
        assert secret_token not in text


def test_workflow_python_version_supported() -> None:
    text = _text()
    assert any(version in text for version in ('"3.10"', '"3.11"', '"3.12"', '"3.13"'))
