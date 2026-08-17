from __future__ import annotations

from performance.measure import (
    _capture,
    budget_failures,
    compare_reports,
    measurement_failures,
    percentile,
    regression_failures,
    summarize,
)


def test_percentile_and_summary_are_deterministic():
    samples = [
        {"ready_ms": 100, "usable_ms": 40, "transfer_bytes": 1000},
        {"ready_ms": 200, "usable_ms": 50, "transfer_bytes": 2000},
        {"ready_ms": 300, "usable_ms": 90, "transfer_bytes": 3000},
    ]
    summary = summarize(samples)
    assert percentile([100, 200, 300], 0.95) == 290
    assert summary["ready_ms_median"] == 200
    assert summary["ready_ms_p95"] == 290
    assert summary["usable_ms_median"] == 50
    assert summary["usable_ms_p95"] == 86
    assert summary["transfer_bytes_median"] == 2000
    assert summary["app_server_ms_median"] is None


def test_budget_failures_report_missing_and_exceeded_metrics():
    report = {
        "routes": {
            "landing": {
                "cold": {"summary": {"ready_ms_p95": 1200}},
            }
        }
    }
    budgets = {
        "routes": {
            "landing": {
                "cold": {"ready_ms_p95": 1000, "app_server_ms_p95": 100},
            },
            "projector": {"cold": {"ready_ms_p95": 1000}},
        }
    }
    failures = budget_failures(report, budgets)
    assert "landing.cold.ready_ms_p95=1200 exceeds budget 1000" in failures
    assert "missing metric: landing.cold.app_server_ms_p95" in failures
    assert "missing measured route: projector" in failures


def test_comparison_and_regression_limit():
    baseline = {
        "routes": {
            "landing": {
                "cold": {"summary": {"ready_ms_median": 1000, "ready_ms_p95": 2000}},
                "warm": {"summary": {"ready_ms_median": 500, "ready_ms_p95": 1000}},
            }
        }
    }
    report = {
        "routes": {
            "landing": {
                "cold": {"summary": {"ready_ms_median": 1250, "ready_ms_p95": 5000}},
                "warm": {"summary": {"ready_ms_median": 450, "ready_ms_p95": 4000}},
            }
        }
    }
    comparison = compare_reports(report, baseline)
    assert comparison["landing"]["cold"]["ready_ms_median"] == 25
    assert comparison["landing"]["cold"]["ready_ms_p95"] == 150
    assert comparison["landing"]["warm"]["ready_ms_median"] == -10
    assert regression_failures(comparison, 20) == [
        "landing.cold.ready_ms_median regressed 25.0% (limit 20%)"
    ]


def test_measurement_failures_reject_error_pages_and_incomplete_samples():
    report = {
        "routes": {
            "landing": {
                "cold": {"samples": [{"status": 503, "quiet": True}]},
                "warm": {"samples": [{"status": 200, "quiet": False, "usable_ms": 10}]},
            }
        }
    }
    assert measurement_failures(report) == [
        "landing.cold[1] returned HTTP 503",
        "landing.cold[1] did not reach the usable UI mark",
        "landing.warm[1] did not reach a quiet window",
    ]


def test_measurement_failures_rejects_missing_usable_mark():
    report = {
        "routes": {
            "landing": {
                "cold": {"samples": [{"status": 200, "quiet": True, "usable_ms": None}]},
                "warm": {"samples": [{"status": 200, "quiet": True, "usable_ms": 25}]},
            }
        }
    }
    assert measurement_failures(report) == [
        "landing.cold[1] did not reach the usable UI mark"
    ]


def test_capture_preserves_navigation_timeout_as_a_failed_sample():
    class FakePage:
        url = "https://prashna.example/"

    def fail_navigation():
        raise TimeoutError("navigation exceeded 30 seconds")

    sample = _capture(FakePage(), fail_navigation, quiet_ms=300, timeout_ms=1000)
    assert sample["status"] is None
    assert sample["quiet"] is False
    assert sample["error"] == "TimeoutError: navigation exceeded 30 seconds"
    assert sample["app_server_ms"] is None
