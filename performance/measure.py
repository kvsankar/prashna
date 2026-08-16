"""Measure cold and warm Prashna browser loads and enforce performance budgets."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

NUMERIC_METRICS = (
    "ready_ms",
    "dcl_ms",
    "load_ms",
    "fcp_ms",
    "transfer_bytes",
    "request_count",
    "app_server_ms",
)


def percentile(values: list[float], pct: float) -> float | None:
    """Return an interpolated percentile without requiring numpy."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 2)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    value = ordered[low] + (ordered[high] - ordered[low]) * (rank - low)
    return round(value, 2)


def summarize(samples: list[dict]) -> dict[str, float | None]:
    summary: dict[str, float | None] = {}
    for metric in NUMERIC_METRICS:
        values = [float(sample[metric]) for sample in samples if sample.get(metric) is not None]
        summary[f"{metric}_median"] = round(statistics.median(values), 2) if values else None
        summary[f"{metric}_p95"] = percentile(values, 0.95)
    return summary


def compare_reports(report: dict, baseline: dict) -> dict:
    """Return percentage changes for summary metrics shared by both reports."""
    comparison: dict[str, dict] = {}
    for route, current_route in report.get("routes", {}).items():
        prior_route = baseline.get("routes", {}).get(route)
        if not prior_route:
            continue
        phases: dict[str, dict] = {}
        for phase in ("cold", "warm"):
            current = current_route.get(phase, {}).get("summary", {})
            prior = prior_route.get(phase, {}).get("summary", {})
            changes = {}
            for metric, current_value in current.items():
                prior_value = prior.get(metric)
                if current_value is None or prior_value in (None, 0):
                    continue
                changes[metric] = round((current_value - prior_value) / prior_value * 100, 2)
            phases[phase] = changes
        comparison[route] = phases
    return comparison


def budget_failures(report: dict, budgets: dict) -> list[str]:
    """Evaluate upper-bound summary budgets."""
    failures = []
    for route, phases in budgets.get("routes", {}).items():
        measured_route = report.get("routes", {}).get(route)
        if not measured_route:
            failures.append(f"missing measured route: {route}")
            continue
        for phase, thresholds in phases.items():
            summary = measured_route.get(phase, {}).get("summary", {})
            for metric, maximum in thresholds.items():
                actual = summary.get(metric)
                if actual is None:
                    failures.append(f"missing metric: {route}.{phase}.{metric}")
                elif actual > maximum:
                    failures.append(
                        f"{route}.{phase}.{metric}={actual} exceeds budget {maximum}"
                    )
    return failures


def regression_failures(comparison: dict, maximum_pct: float) -> list[str]:
    failures = []
    for route, phases in comparison.items():
        for phase, metrics in phases.items():
            for metric, change in metrics.items():
                if change > maximum_pct:
                    failures.append(
                        f"{route}.{phase}.{metric} regressed {change}% (limit {maximum_pct}%)"
                    )
    return failures


def measurement_failures(report: dict) -> list[str]:
    """Reject incomplete navigations so a fast error page cannot pass a budget."""
    failures = []
    for route, phases in report.get("routes", {}).items():
        for phase in ("cold", "warm"):
            for index, sample in enumerate(phases.get(phase, {}).get("samples", []), 1):
                status = sample.get("status")
                if status is None or status >= 400:
                    failures.append(f"{route}.{phase}[{index}] returned HTTP {status}")
                if not sample.get("quiet"):
                    failures.append(f"{route}.{phase}[{index}] did not reach a quiet window")
    return failures


def _wait_for_quiet(page, *, quiet_ms: int, timeout_ms: int) -> bool:
    """Wait until the resource count is stable; WebSockets do not block this."""
    deadline = time.perf_counter() + timeout_ms / 1000
    stable_since = time.perf_counter()
    last_count = -1
    while time.perf_counter() < deadline:
        count = page.evaluate("performance.getEntriesByType('resource').length")
        if count != last_count:
            last_count = count
            stable_since = time.perf_counter()
        elif (time.perf_counter() - stable_since) * 1000 >= quiet_ms:
            return True
        page.wait_for_timeout(50)
    return False


def _capture(page, navigate, *, quiet_ms: int, timeout_ms: int) -> dict:
    started = time.perf_counter()
    response = navigate()
    quiet = _wait_for_quiet(page, quiet_ms=quiet_ms, timeout_ms=timeout_ms)
    ready_ms = round((time.perf_counter() - started) * 1000, 2)
    timing = page.evaluate(
        """() => {
          const nav = performance.getEntriesByType('navigation')[0];
          const resources = performance.getEntriesByType('resource');
          const paints = Object.fromEntries(
            performance.getEntriesByType('paint').map(p => [p.name, p.startTime]));
          const all = [nav, ...resources].filter(Boolean);
          const app = all.flatMap(e => (e.serverTiming || []))
            .filter(t => t.name === 'app').map(t => t.duration);
          return {
            dcl_ms: nav ? nav.domContentLoadedEventEnd : null,
            load_ms: nav ? nav.loadEventEnd : null,
            fcp_ms: paints['first-contentful-paint'] ?? null,
            transfer_bytes: all.reduce((n, e) => n + (e.transferSize || 0), 0),
            request_count: all.length,
            app_server_ms: app.length ? Math.max(...app) : null,
            protocols: [...new Set(all.map(e => e.nextHopProtocol).filter(Boolean))],
            slowest: resources.map(r => ({name: r.name, ms: r.duration, bytes: r.transferSize || 0}))
              .sort((a, b) => b.ms - a.ms).slice(0, 5),
          };
        }"""
    )
    for item in timing["slowest"]:
        parsed = urlparse(item["name"])
        item["name"] = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        item["ms"] = round(item["ms"], 2)
    return {
        "status": response.status if response else None,
        "final_path": urlparse(page.url).path,
        "ready_ms": ready_ms,
        "quiet": quiet,
        **timing,
    }


def _parse_routes(values: list[str], session_code: str | None) -> dict[str, str]:
    if values:
        routes = {}
        for value in values:
            if "=" not in value:
                raise ValueError(f"route must be NAME=PATH: {value}")
            name, path = value.split("=", 1)
            routes[name] = path
        return routes
    routes = {"landing": "/"}
    if session_code:
        routes["moderator"] = f"/m/{session_code}"
        routes["projector"] = f"/p/{session_code}"
    return routes


def _authenticate_context(context, args) -> None:
    if args.moderator_key_env and args.session_code:
        key = os.environ.get(args.moderator_key_env)
        if not key:
            raise RuntimeError(f"missing environment variable: {args.moderator_key_env}")
        context.add_init_script(
            f"localStorage.setItem({json.dumps('mod_key:' + args.session_code)}, {json.dumps(key)});"
        )
    if args.admin_username_env or args.admin_password_env:
        username = os.environ.get(args.admin_username_env or "")
        password = os.environ.get(args.admin_password_env or "")
        if not username or not password:
            raise RuntimeError("both admin credential environment variables must be set")
        response = context.request.post(
            urljoin(args.base_url, "/api/admin/login"),
            data={"username": username, "password": password},
        )
        if not response.ok:
            raise RuntimeError(f"admin login failed with HTTP {response.status}")


def measure(args) -> dict:
    from playwright.sync_api import sync_playwright

    routes = _parse_routes(args.route, args.session_code)
    report = {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url.rstrip("/"),
        "runs": args.runs,
        "quiet_ms": args.quiet_ms,
        "routes": {},
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for name, path in routes.items():
            cold_samples = []
            warm_samples = []
            for _ in range(args.runs):
                context = browser.new_context()
                _authenticate_context(context, args)
                page = context.new_page()
                url = urljoin(args.base_url.rstrip("/") + "/", path.lstrip("/"))
                cold_samples.append(
                    _capture(
                        page,
                        lambda url=url: page.goto(url, wait_until="load", timeout=args.timeout_ms),
                        quiet_ms=args.quiet_ms,
                        timeout_ms=args.timeout_ms,
                    )
                )
                warm_samples.append(
                    _capture(
                        page,
                        lambda: page.reload(wait_until="load", timeout=args.timeout_ms),
                        quiet_ms=args.quiet_ms,
                        timeout_ms=args.timeout_ms,
                    )
                )
                context.close()
            report["routes"][name] = {
                "path": path,
                "cold": {"samples": cold_samples, "summary": summarize(cold_samples)},
                "warm": {"samples": warm_samples, "summary": summarize(warm_samples)},
            }
        browser.close()
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--session-code")
    parser.add_argument("--route", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--quiet-ms", type=int, default=300)
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--max-regression-percent", type=float)
    parser.add_argument("--moderator-key-env")
    parser.add_argument("--admin-username-env")
    parser.add_argument("--admin-password-env")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    report = measure(args)
    failures = measurement_failures(report)
    if args.baseline:
        baseline = json.loads(args.baseline.read_text())
        report["comparison"] = compare_reports(report, baseline)
        if args.max_regression_percent is not None:
            failures.extend(
                regression_failures(report["comparison"], args.max_regression_percent)
            )
    if args.budget:
        failures.extend(budget_failures(report, json.loads(args.budget.read_text())))
    report["failures"] = failures
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        sys.stdout.write(rendered)
    if failures:
        for failure in failures:
            print(f"PERF FAILURE: {failure}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
