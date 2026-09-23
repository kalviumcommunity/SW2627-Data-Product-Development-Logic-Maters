"""Automated email delivery for generated stakeholder reports.

Sends a report built by :mod:`reports.report_generator` to configured
recipients over SMTP (stdlib only). This module contains no analytics of
its own: every figure comes from ``build_report`` over the run's own
integrated output.

Configuration comes from environment variables only — never hardcoded,
never committed, never logged::

    REPORT_SMTP_HOST      SMTP server hostname (required)
    REPORT_SMTP_PORT      SMTP port (default 587)
    REPORT_SMTP_USERNAME  SMTP username (optional; required by most servers)
    REPORT_SMTP_PASSWORD  SMTP password (optional; required by most servers)
    REPORT_EMAIL_FROM     Sender address (required; falls back to username)
    REPORT_EMAIL_TO       Recipient list, comma-separated (required unless
                          ``--to`` is passed)

Legacy ``EMAIL_HOST`` / ``EMAIL_PORT`` / ``EMAIL_USERNAME`` /
``EMAIL_PASSWORD`` / ``EMAIL_RECIPIENT`` names are accepted as fallbacks
for the values above (see ``.env.example``). Canonical names are the
``REPORT_*`` ones.

CLI::

    python -m reports.email_report --run data/processed/runs/run_<id>.json
    python -m reports.email_report --run data/processed/runs/run_<id>.json --to ops@example.com
    python -m reports.email_report --run data/processed/runs/run_<id>.json --dry-run

Exit codes: 0 on success (or dry-run validation), 1 on configuration or
report errors, 2 on SMTP delivery failure. Tests never send real email:
pass a fake SMTP class instead (see ``tests/test_email_report.py``).
"""

from __future__ import annotations

import argparse
import html
import os
import smtplib
import sys
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence, Union

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reports.report_generator import build_report, render_html, render_markdown

PathLike = Union[str, Path]

# Canonical variable names (documented in .env.example).
VAR_HOST = "REPORT_SMTP_HOST"
VAR_PORT = "REPORT_SMTP_PORT"
VAR_USERNAME = "REPORT_SMTP_USERNAME"
VAR_PASSWORD = "REPORT_SMTP_PASSWORD"
VAR_FROM = "REPORT_EMAIL_FROM"
VAR_TO = "REPORT_EMAIL_TO"

DEFAULT_SMTP_PORT = 587
SMTP_TIMEOUT_SECONDS = 30


class EmailConfigError(ValueError):
    """Raised when email configuration or recipients are missing/invalid."""


class EmailSendError(RuntimeError):
    """Raised when SMTP delivery fails (credentials never included)."""


@dataclass
class EmailConfig:
    """Validated SMTP configuration (password held in memory only)."""

    smtp_host: str
    smtp_port: int = DEFAULT_SMTP_PORT
    username: Optional[str] = None
    password: Optional[str] = None
    email_from: str = ""
    email_to: list[str] = field(default_factory=list)

    def safe_summary(self) -> str:
        """Log-safe one-liner: host/port/from/recipients, never secrets."""
        recipients = ", ".join(self.email_to)
        return (
            f"host={self.smtp_host} port={self.smtp_port} "
            f"from={self.email_from} to={recipients}"
        )


def _lookup(env: Mapping[str, str], *names: str) -> str:
    """First non-blank value for any of ``names`` (empty string if none)."""
    for name in names:
        value = env.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_recipients(raw: Union[str, Sequence[str]]) -> list[str]:
    """Split a recipient string/list on commas/semicolons (validated)."""
    if isinstance(raw, str):
        parts: list[str] = []
        for chunk in raw.replace(";", ",").split(","):
            item = chunk.strip()
            if item:
                parts.append(item)
    else:
        parts = [str(item).strip() for item in raw if str(item).strip()]
    for address in parts:
        if "@" not in address or " " in address:
            raise EmailConfigError(
                f"Invalid email recipient: {address!r} (expected name@domain)."
            )
    return parts


def load_email_config(
    to_override: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> EmailConfig:
    """Build an :class:`EmailConfig` from the environment (+ CLI override).

    Raises:
        EmailConfigError: With an actionable message naming the missing
            variable(s). The message never contains secret values.
    """
    source: Mapping[str, str] = os.environ if env is None else env
    host = _lookup(source, VAR_HOST, "EMAIL_HOST")
    port_raw = _lookup(source, VAR_PORT, "EMAIL_PORT") or str(DEFAULT_SMTP_PORT)
    username = _lookup(source, VAR_USERNAME, "EMAIL_USERNAME") or None
    password = _lookup(source, VAR_PASSWORD, "EMAIL_PASSWORD") or None
    email_from = (
        _lookup(source, VAR_FROM, "EMAIL_FROM") or username or ""
    )
    recipients_raw = (
        to_override.strip()
        if to_override is not None and to_override.strip()
        else _lookup(source, VAR_TO, "EMAIL_RECIPIENT", "EMAIL_TO")
    )

    missing: list[str] = []
    if not host:
        missing.append(f"{VAR_HOST} (fallback EMAIL_HOST)")
    if not email_from:
        missing.append(f"{VAR_FROM} (fallback EMAIL_FROM, else {VAR_USERNAME})")
    if missing:
        raise EmailConfigError(
            "Email configuration missing: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and set real values locally; "
            "never commit credentials."
        )
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise EmailConfigError(
            f"Invalid {VAR_PORT}: {port_raw!r} (expected an integer port)."
        ) from exc
    if not 1 <= port <= 65535:
        raise EmailConfigError(
            f"Invalid {VAR_PORT}: {port} (expected 1-65535)."
        )
    if not recipients_raw:
        raise EmailConfigError(
            f"No email recipients configured: set {VAR_TO} "
            "(fallback EMAIL_RECIPIENT) or pass --to recipient@example.com."
        )
    recipients = parse_recipients(recipients_raw)
    if not recipients:
        raise EmailConfigError(
            f"No email recipients configured: set {VAR_TO} "
            "(fallback EMAIL_RECIPIENT) or pass --to recipient@example.com."
        )
    return EmailConfig(
        smtp_host=host,
        smtp_port=port,
        username=username,
        password=password,
        email_from=email_from,
        email_to=recipients,
    )


def build_subject(report: Mapping[str, Any]) -> str:
    """Operational subject: product — dataset — run id (no invented data)."""
    dataset = report.get("dataset", "unknown")
    run_id = report.get("run_id", "unknown")
    return f"Cascading Delay Intelligence Report — {dataset} — {run_id}"


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return "N/A"
    except (TypeError, ValueError):
        pass
    if isinstance(value, float):
        return f"{value:,.{digits}f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _route_risk_summary(report: Mapping[str, Any]) -> str:
    rows = report.get("risk_table") or []
    rated = [r for r in rows if r.get("cascade_probability") is not None]
    if not rated:
        return "No routes with observed delays in this run."
    top = max(rated, key=lambda r: float(r["cascade_probability"]))
    return (
        f"Highest observed historical cascade rate: route {top.get('route')} "
        f"({_fmt(top.get('cascade_rate'))}%, "
        f"P(downstream|initial)={_fmt(top.get('cascade_probability'), digits=3)}, "
        f"{_fmt(top.get('cascade_shipments'))} of "
        f"{_fmt(top.get('delayed_shipments'))} delayed shipments cascaded; "
        f"historical observation, not a prediction)."
    )


def render_summary_text(report: Mapping[str, Any]) -> str:
    """Concise plain-text summary (operationally useful, never prescriptive)."""
    kpis = report.get("kpis", {}) or {}
    cascade = report.get("cascade", {}) or {}
    alerts = report.get("alerts", {}) or {}
    warnings = report.get("warnings", []) or []
    validation = report.get("validation_summary", {}) or {}
    lines = [
        "Cascading Delay Intelligence — report summary",
        f"Dataset: {report.get('dataset', 'unknown')} "
        f"({report.get('source_label', '')})",
        f"Run: {report.get('run_id', 'unknown')} "
        f"· status {report.get('overall_status', 'UNKNOWN')}",
        f"Shipments: {_fmt(kpis.get('total_shipments'))} "
        f"· delayed {_fmt(kpis.get('delayed_shipments'))} "
        f"(delay rate {_fmt(kpis.get('delay_rate'))}%)",
        f"Cascades: {_fmt(cascade.get('candidate_count'))} candidates "
        f"(rate {_fmt(cascade.get('candidate_rate'))}%, "
        f"avg depth {_fmt(cascade.get('avg_depth'))}, "
        f"max depth {_fmt(cascade.get('max_depth'))})",
        f"Route risk: {_route_risk_summary(report)}",
        f"Alerts: {_fmt(alerts.get('total'))}",
    ]
    if validation:
        lines.append(
            "Validation: "
            + ", ".join(
                f"{name}: {info.get('status', 'UNKNOWN')}"
                for name, info in sorted(validation.items())
            )
        )
    if warnings:
        lines.append(f"Warnings ({len(warnings)}):")
        for warning in warnings[:10]:
            lines.append(f"  - {warning}")
        if len(warnings) > 10:
            lines.append(f"  … and {len(warnings) - 10} more (see full report).")
    else:
        lines.append("Warnings: none recorded for this run.")
    lines.append(
        "Note: risk figures are historical empirical observations, not ML "
        "predictions. Patterns describe associations, not proven causes."
    )
    return "\n".join(lines) + "\n"


def render_summary_html(report: Mapping[str, Any]) -> str:
    """HTML fragment for the email body (summary only; full report attached)."""
    kpis = report.get("kpis", {}) or {}
    cascade = report.get("cascade", {}) or {}
    alerts = report.get("alerts", {}) or {}
    warnings = report.get("warnings", []) or []
    validation = report.get("validation_summary", {}) or {}

    def row(label: str, value: str) -> str:
        return (
            f"<tr><th>{html.escape(label)}</th>"
            f"<td>{html.escape(value)}</td></tr>"
        )

    parts = [
        "<h2>Cascading Delay Intelligence — report summary</h2>",
        "<table>",
        row("Dataset",
            f"{report.get('dataset', 'unknown')} "
            f"({report.get('source_label', '')})"),
        row("Run",
            f"{report.get('run_id', 'unknown')} "
            f"· status {report.get('overall_status', 'UNKNOWN')}"),
        row("Shipments",
            f"{_fmt(kpis.get('total_shipments'))} · delayed "
            f"{_fmt(kpis.get('delayed_shipments'))} "
            f"(delay rate {_fmt(kpis.get('delay_rate'))}%)"),
        row("Cascades",
            f"{_fmt(cascade.get('candidate_count'))} candidates "
            f"(rate {_fmt(cascade.get('candidate_rate'))}%)"),
        row("Route risk", _route_risk_summary(report)),
        row("Alerts", f"{_fmt(alerts.get('total'))}"),
        "</table>",
    ]
    if validation:
        parts.append("<h3>Validation</h3><ul>")
        for name, info in sorted(validation.items()):
            parts.append(
                f"<li>{html.escape(str(name))}: "
                f"{html.escape(str(info.get('status', 'UNKNOWN')))}</li>"
            )
        parts.append("</ul>")
    if warnings:
        parts.append(f"<h3>Warnings ({len(warnings)})</h3><ul>")
        for warning in warnings[:10]:
            parts.append(f"<li>{html.escape(str(warning))}</li>")
        parts.append("</ul>")
    parts.append(
        "<p><em>Risk figures are historical empirical observations, not ML "
        "predictions. Patterns describe associations, not proven causes. "
        "The full Markdown/HTML report is attached.</em></p>"
    )
    return "\n".join(parts)


def build_message(
    config: EmailConfig,
    report: Mapping[str, Any],
    html_report: str,
    markdown_report: str,
    attach_reports: bool = True,
) -> EmailMessage:
    """Assemble the MIME message (summary body + optional full attachments)."""
    message = EmailMessage()
    message["Subject"] = build_subject(report)
    message["From"] = config.email_from
    message["To"] = ", ".join(config.email_to)
    message.set_content(render_summary_text(report))
    message.add_alternative(render_summary_html(report), subtype="html")
    if attach_reports:
        run_id = str(report.get("run_id", "report"))
        message.add_attachment(
            markdown_report.encode("utf-8"),
            maintype="text",
            subtype="markdown",
            filename=f"report_{run_id}.md",
        )
        message.add_attachment(
            html_report.encode("utf-8"),
            maintype="text",
            subtype="html",
            filename=f"report_{run_id}.html",
        )
    return message


def send_message(
    config: EmailConfig,
    message: EmailMessage,
    smtp_class: Optional[Callable[..., Any]] = None,
) -> None:
    """Deliver ``message`` via SMTP (injected class for tests).

    Raises:
        EmailSendError: On any transport/auth failure. The error never
            contains the password or the full message payload.
    """
    factory = smtp_class if smtp_class is not None else smtplib.SMTP
    try:
        server = factory(
            config.smtp_host, config.smtp_port,
            timeout=SMTP_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise EmailSendError(
            f"Could not connect to SMTP {config.smtp_host}:"
            f"{config.smtp_port} ({type(exc).__name__}: {exc})."
        ) from exc
    try:
        if hasattr(server, "__enter__"):
            context = server
        else:  # pragma: no cover - non-context SMTP doubles
            from contextlib import nullcontext

            context = nullcontext(server)  # type: ignore[arg-type]
        with context as smtp:
            try:
                smtp.ehlo()
            except Exception:  # pragma: no cover - server greeting quirks
                pass
            if config.smtp_port == DEFAULT_SMTP_PORT and hasattr(smtp, "starttls"):
                try:
                    smtp.starttls()
                    smtp.ehlo()
                except Exception:  # pragma: no cover - plain local relays
                    pass
            if config.username:
                try:
                    smtp.login(config.username, config.password or "")
                except Exception as exc:
                    raise EmailSendError(
                        f"SMTP authentication failed for host "
                        f"{config.smtp_host} (user "
                        f"{config.username}): {type(exc).__name__}."
                    ) from exc
            try:
                smtp.send_message(message)
            except Exception as exc:
                raise EmailSendError(
                    f"SMTP delivery to {', '.join(config.email_to)} failed "
                    f"({type(exc).__name__}: {exc})."
                ) from exc
    finally:
        close = getattr(server, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover - best effort
                pass


def send_report_for_run(
    manifest_path: PathLike,
    to_override: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    smtp_class: Optional[Callable[..., Any]] = None,
    attach_reports: bool = True,
) -> dict[str, Any]:
    """Load a run, build its report, and email it (single seam for CLI/tests).

    Returns a JSON-friendly summary (recipients, subject, attachment names —
    never credentials).
    """
    report = build_report(manifest_path)
    markdown_report = render_markdown(report)
    html_report = render_html(report)
    config = load_email_config(to_override=to_override, env=env)
    message = build_message(
        config, report, html_report, markdown_report,
        attach_reports=attach_reports,
    )
    send_message(config, message, smtp_class=smtp_class)
    attachments = (
        [f"report_{report.get('run_id')}.md",
         f"report_{report.get('run_id')}.html"]
        if attach_reports else []
    )
    return {
        "run_id": report.get("run_id"),
        "dataset": report.get("dataset"),
        "subject": build_subject(report),
        "recipients": list(config.email_to),
        "sender": config.email_from,
        "smtp_host": config.smtp_host,
        "smtp_port": config.smtp_port,
        "attachments": attachments,
    }


def build_parser() -> argparse.ArgumentParser:
    """CLI definition (help text doubles as usage documentation)."""
    parser = argparse.ArgumentParser(
        prog="reports.email_report",
        description=(
            "Email a stakeholder report for a pipeline run. The report is "
            "built from the run manifest with reports.report_generator; "
            "credentials come from environment variables only."
        ),
    )
    parser.add_argument(
        "--run", required=True,
        help="Path to the run manifest JSON (data/processed/runs/run_<id>.json).",
    )
    parser.add_argument(
        "--to", default=None,
        help="Recipient override, comma-separated (else REPORT_EMAIL_TO).",
    )
    parser.add_argument(
        "--no-attachments", action="store_true",
        help="Send the summary body only (default attaches Markdown+HTML).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate configuration and build the email without sending.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point: 0 sent/valid, 1 config/report error, 2 SMTP failure."""
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.run)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Email delivery failed: {exc}")
        return 1
    try:
        config = load_email_config(to_override=args.to)
    except EmailConfigError as exc:
        print(f"Email configuration error: {exc}")
        return 1
    markdown_report = render_markdown(report)
    html_report = render_html(report)
    message = build_message(
        config, report, html_report, markdown_report,
        attach_reports=not args.no_attachments,
    )
    if args.dry_run:
        print(f"Subject: {message['Subject']}")
        print(f"Validated: {config.safe_summary()}")
        print("Dry run: email not sent.")
        return 0
    try:
        send_message(config, message)
    except EmailSendError as exc:
        print(f"Email delivery failed: {exc}")
        return 2
    print(f"Email sent: {message['Subject']} -> {', '.join(config.email_to)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
