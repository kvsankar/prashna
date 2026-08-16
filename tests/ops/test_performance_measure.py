from __future__ import annotations

from performance.measure import (
    budget_failures,
    compare_reports,
    measurement_failures,
    percentile,
    regression_failures,
    summarize,
)


def test_percentile_and_summary_are_deterministic():
    samples = [
        {"ready_ms": 100, "transfer_bytes": 1000},
        {"ready_ms": 200, "transfer_bytes": 2000},
        {"ready_ms": 300, "transfer_bytes": 3000},
    ]
    summary = summarize(samples)
    assert percentile([100, 200, 300], 0.95) == 290
    assert summary["ready_ms_median"] == 200
    assert summary["ready_ms_p95"] == 290
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
                "cold": {"summary": {"ready_ms_p95": 1000}},
                "warm": {"summary": {"ready_ms_p95": 500}},
            }
        }
    }
    report = {
        "routes": {
            "landing": {
                "cold": {"summary": {"ready_ms_p95": 1250}},
                "warm": {"summary": {"ready_ms_p95": 450}},
            }
        }
    }
    comparison = compare_reports(report, baseline)
    assert comparison["landing"]["cold"]["ready_ms_p95"] == 25
    assert comparison["landing"]["warm"]["ready_ms_p95"] == -10
    assert regression_failures(comparison, 20) == [
        "landing.cold.ready_ms_p95 regressed 25.0% (limit 20%)"
    ]


def test_measurement_failures_reject_error_pages_and_incomplete_samples():
    report = {
        "routes": {
            "landing": {
                "cold": {"samples": [{"status": 503, "quiet": True}]},
                "warm": {"samples": [{"status": 200, "quiet": False}]},
            }
        }
    }
    assert measurement_failures(report) == [
        "landing.cold[1] returned HTTP 503",
        "landing.warm[1] did not reach a quiet window",
    ]
