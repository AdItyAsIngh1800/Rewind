"""Deterministic evidence-grounded reports. Any LLM layer sits behind this, never in front."""

from services.reporting.generator import GENERATOR_VERSION, ReportError, generate_report
from services.reporting.persistence import report_for_incident, write_report

__all__ = [
    "GENERATOR_VERSION",
    "ReportError",
    "generate_report",
    "report_for_incident",
    "write_report",
]
