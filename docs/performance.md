# Performance measurement and operations

Prashna performance is measured at three layers so a fast API response is not
mistaken for a fast page:

1. `Server-Timing: app;dur=...` reports time spent in the FastAPI application.
2. Browser navigation/resource timing reports cold and repeat page loads,
   transfers, request counts, paint milestones, and negotiated HTTP protocol.
3. Structured request logs retain slow requests and state-changing request
   durations for production diagnosis.

The repeatable browser runner, budgets, report format, and authenticated usage
are documented in [`performance/README.md`](../performance/README.md).

## 2026-08-16 production baseline

Five exploratory cold browser contexts showed roughly 2.1 to 2.3 seconds for
the landing, projector, and moderator-entry pages from the measurement host.
All resources negotiated HTTP/1.1. By contrast, direct requests inside the
application host were generally 3 to 8 ms, the larger authenticated list APIs
were generally 5 to 42 ms, and no GET request at or above one second appeared
in the preceding 24 hours of container logs. The database was under 0.4 MB and
the container was using about 68 MiB of memory.

This evidence locates the observed delay primarily in network round trips and
cold browser delivery, not in current CPU, memory, or SQLite capacity. A
baseline is specific to its measurement host and network; compare releases
from the same location and retain the JSON reports.

## Implemented fixes

- Fingerprinted Vite assets receive a one-year immutable cache policy.
- Responses of at least 1,000 bytes are gzip-compressed by the application.
- HTTPS is upgraded to HTTP/2 by an idempotent deployment helper that takes a
  timestamped backup, validates nginx, reloads only on success, and restores on
  validation failure.
- Projector reads are explicitly display-only and do not create participant
  identities.
- The first WebSocket connection no longer repeats each page's initial API
  load; a true reconnect still performs a catch-up refresh.
- Moderator WebSocket events refresh only affected panels, with a safe full
  refresh for reconnects and unknown event types.
- Admin/session summary endpoints count related rows in SQL instead of loading
  full child collections and answer/submission trees.
- Independent first-load requests run concurrently, while lower-priority
  moderator panels no longer block the operational controls.

## Release verification

For every performance-sensitive release:

1. Run lint and the full automated suite.
2. Save a pre-release browser JSON report where practical.
3. Deploy the immutable image revision.
4. Verify container health, `/api/admin/status`, and a direct static page.
5. Run the browser measurement again and compare cold and repeat samples.
6. Confirm the public endpoint negotiates HTTP/2, static assets are immutable
   and compressed, and API responses expose `Server-Timing` with `no-store`.

Absolute budgets catch severe regressions; they do not replace comparisons,
resource inspection, or application timing. Network variance means a single
public request is not useful release evidence.
