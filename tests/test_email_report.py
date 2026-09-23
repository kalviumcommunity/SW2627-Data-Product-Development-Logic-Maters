"""Tests for reports/email_report.py (mocked SMTP only — never real email)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.run_pipeline import run_pipeline
from reports import email_report
from reports.email_report import (
    EmailConfigError,
    EmailSendError,
    build_message,
    build_subject,
    load_email_config,
    parse_recipients,
    render_summary_html,
    render_summary_text,
    send_message,
    send_report_for_run,
)


@pytest.fixture(scope="module")
def showcase_manifest(tmp_path_factory: pytest.TempPathFactory) -> dict:
    tmp_path = tmp_path_factory.mktemp("email_showcase")
    manifest = run_pipeline(
        dataset="showcase",
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        runs_dir=tmp_path / "runs",
        output_path=tmp_path / "integrated.csv",
        seed=11,
        n_shipments=100,
    )
    return {"manifest": manifest, "path": Path(manifest["manifest_path"])}


@pytest.fixture()
def report_dict(showcase_manifest: dict) -> dict:
    from reports.report_generator import build_report

    return build_report(showcase_manifest["path"])


def _env(**overrides: str) -> dict:
    base = {
        "REPORT_SMTP_HOST": "smtp.example.com",
        "REPORT_SMTP_PORT": "587",
        "REPORT_SMTP_USERNAME": "sender@example.com",
        "REPORT_SMTP_PASSWORD": "s3cret-placeholder",
        "REPORT_EMAIL_FROM": "sender@example.com",
        "REPORT_EMAIL_TO": "ops@example.com",
    }
    base.update(overrides)
    return base


class FakeSMTP:
    """Minimal smtplib.SMTP double recording delivery (no network)."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: int = 30) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.messages: list = []
        self.logins: list = []
        self.starttls_called = False
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def ehlo(self) -> None:
        return None

    def starttls(self) -> None:
        self.starttls_called = True

    def login(self, user: str, password: str) -> None:
        self.logins.append((user, password))

    def send_message(self, message) -> None:
        self.messages.append(message)

    def close(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _clear_fake_instances():
    FakeSMTP.instances.clear()
    yield
    FakeSMTP.instances.clear()


# -- construction / recipients / subject ------------------------------------


def test_successful_email_construction(report_dict: dict) -> None:
    config = load_email_config(env=_env())
    message = build_message(config, report_dict, "<html></html>", "# md")
    assert message["From"] == "sender@example.com"
    assert message["To"] == "ops@example.com"
    assert "Cascading Delay Intelligence Report" in message["Subject"]


def test_correct_recipient_handling(report_dict: dict) -> None:
    config = load_email_config(
        to_override="a@example.com, b@example.com ;c@example.com",
        env=_env(),
    )
    assert config.email_to == ["a@example.com", "b@example.com", "c@example.com"]
    message = build_message(config, report_dict, "<html></html>", "# md")
    assert message["To"] == "a@example.com, b@example.com, c@example.com"
    # CLI --to overrides the environment list.
    assert parse_recipients("x@example.com;y@example.com") == [
        "x@example.com",
        "y@example.com",
    ]
    with pytest.raises(EmailConfigError, match="Invalid email recipient"):
        parse_recipients("not-an-email")


def test_subject_generation(report_dict: dict) -> None:
    subject = build_subject(report_dict)
    assert subject.startswith("Cascading Delay Intelligence Report — ")
    assert report_dict["dataset"] in subject
    assert report_dict["run_id"] in subject


def test_report_attachment_and_body(report_dict: dict) -> None:
    from reports.report_generator import render_html, render_markdown

    config = load_email_config(env=_env())
    html_report = render_html(report_dict)
    markdown_report = render_markdown(report_dict)
    message = build_message(config, report_dict, html_report, markdown_report)
    # Summary body present in both plain and HTML alternatives.
    plain = message.get_body(preferencelist=("plain",)).get_content()
    assert "Shipments" in plain
    assert "Cascades" in plain
    assert "Alerts" in plain
    assert "not ML" in plain or "not ml" in plain.lower()
    filenames = [part.get_filename() for part in message.iter_attachments()]
    assert f"report_{report_dict['run_id']}.md" in filenames
    assert f"report_{report_dict['run_id']}.html" in filenames
    # Summary HTML fragment contains the operational fields.
    summary_html = render_summary_html(report_dict)
    for token in ("Shipments", "Cascades", "Alerts", "Route risk"):
        assert token in summary_html
    summary_text = render_summary_text(report_dict)
    for token in ("Shipments", "Cascades", "Alerts", "Warnings"):
        assert token in summary_text
    # No invented recommendations.
    for forbidden in ("recommend", "you should fix", "predicted"):
        assert forbidden not in summary_text.lower()


def test_summary_matches_pipeline_values(
    report_dict: dict, showcase_manifest: dict
) -> None:
    detail = showcase_manifest["manifest"]["stages"]["analytics"]["detail"]["kpis"]
    summary = render_summary_text(report_dict)
    assert f"{detail['total_shipments']:,}" in summary
    assert f"{detail['delayed_shipments']:,}" in summary


# -- configuration failures --------------------------------------------------


def test_missing_smtp_configuration() -> None:
    with pytest.raises(EmailConfigError, match="REPORT_SMTP_HOST"):
        load_email_config(env={})
    with pytest.raises(EmailConfigError, match="REPORT_SMTP_HOST"):
        load_email_config(env=_env(REPORT_SMTP_HOST=""))


def test_missing_recipient() -> None:
    env = _env(REPORT_EMAIL_TO="")
    with pytest.raises(EmailConfigError, match="No email recipients"):
        load_email_config(env=env)
    # CLI override rescues a missing env recipient list.
    config = load_email_config(to_override="ops@example.com", env=env)
    assert config.email_to == ["ops@example.com"]


def test_missing_sender() -> None:
    env = _env(REPORT_EMAIL_FROM="", REPORT_SMTP_USERNAME="")
    with pytest.raises(EmailConfigError, match="REPORT_EMAIL_FROM"):
        load_email_config(env=env)


def test_invalid_port() -> None:
    with pytest.raises(EmailConfigError, match="Invalid REPORT_SMTP_PORT"):
        load_email_config(env=_env(REPORT_SMTP_PORT="not-a-port"))


def test_legacy_env_fallbacks_accepted() -> None:
    legacy = {
        "EMAIL_HOST": "legacy.example.com",
        "EMAIL_PORT": "2525",
        "EMAIL_USERNAME": "legacy@example.com",
        "EMAIL_PASSWORD": "legacy-secret",
        "EMAIL_RECIPIENT": "team@example.com",
    }
    config = load_email_config(env=legacy)
    assert config.smtp_host == "legacy.example.com"
    assert config.smtp_port == 2525
    assert config.email_from == "legacy@example.com"
    assert config.email_to == ["team@example.com"]


# -- transport ----------------------------------------------------------------


def test_send_via_mock_smtp(report_dict: dict) -> None:
    config = load_email_config(env=_env())
    message = build_message(config, report_dict, "<html></html>", "# md")
    send_message(config, message, smtp_class=FakeSMTP)
    assert len(FakeSMTP.instances) == 1
    server = FakeSMTP.instances[0]
    assert (server.host, server.port) == ("smtp.example.com", 587)
    assert server.logins == [("sender@example.com", "s3cret-placeholder")]
    assert len(server.messages) == 1


def test_smtp_failure_raises_without_secrets() -> None:
    class BoomSMTP(FakeSMTP):
        def send_message(self, message) -> None:  # type: ignore[override]
            raise ConnectionError("relay down")

    config = load_email_config(env=_env())
    from reports.report_generator import build_report  # noqa: F401 (import guard)

    message = build_message(
        config,
        {"run_id": "r1", "dataset": "showcase", "kpis": {},
         "cascade": {"candidate_count": 0}, "alerts": {"total": 0},
         "warnings": [], "validation_summary": {}, "risk_table": [],
         "source_label": "x"},
        "<html></html>",
        "# md",
    )
    with pytest.raises(EmailSendError, match="SMTP delivery") as exc_info:
        send_message(config, message, smtp_class=BoomSMTP)
    assert "s3cret-placeholder" not in str(exc_info.value)


def test_no_credentials_leaked_in_logs_or_summary(
    report_dict: dict, capsys: pytest.CaptureFixture
) -> None:
    config = load_email_config(env=_env())
    print(config.safe_summary())
    print(render_summary_text(report_dict))
    print(render_summary_html(report_dict))
    out = capsys.readouterr().out
    assert "s3cret-placeholder" not in out
    assert "smtp" not in out.lower() or "smtp.example.com" in out
    message = build_message(
        config, report_dict, "<html>body</html>", "# body",
    )
    assert "s3cret-placeholder" not in message.as_string()


def test_no_secrets_written_to_generated_files(
    report_dict: dict, tmp_path: Path
) -> None:
    from reports.report_generator import render_html, render_markdown

    html_report = render_html(report_dict)
    markdown_report = render_markdown(report_dict)
    (tmp_path / "report.md").write_text(markdown_report, encoding="utf-8")
    (tmp_path / "report.html").write_text(html_report, encoding="utf-8")
    for path in (tmp_path / "report.md", tmp_path / "report.html"):
        prose = path.read_text(encoding="utf-8").lower()
        for secret in ("password", "api_key", "smtp", "bearer "):
            assert secret not in prose


def test_end_to_end_send_mocked(showcase_manifest: dict) -> None:
    result = send_report_for_run(
        showcase_manifest["path"],
        env=_env(),
        smtp_class=FakeSMTP,
    )
    assert result["run_id"] == showcase_manifest["manifest"]["run_id"]
    assert result["recipients"] == ["ops@example.com"]
    assert "Cascading Delay Intelligence Report" in result["subject"]
    assert result["attachments"] == [
        f"report_{result['run_id']}.md",
        f"report_{result['run_id']}.html",
    ]
    assert len(FakeSMTP.instances) == 1


def test_cli_dry_run_and_failures(
    showcase_manifest: dict, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    path = str(showcase_manifest["path"])
    monkeypatch.setenv("REPORT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("REPORT_EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("REPORT_EMAIL_TO", "ops@example.com")
    assert email_report.main(["--run", path, "--dry-run"]) == 0
    assert "Dry run" in capsys.readouterr().out

    monkeypatch.delenv("REPORT_SMTP_HOST", raising=False)
    monkeypatch.delenv("EMAIL_HOST", raising=False)
    assert email_report.main(["--run", path, "--dry-run"]) == 1
    assert "configuration" in capsys.readouterr().out.lower()

    assert email_report.main(["--run", str("nope/missing.json")]) == 1
