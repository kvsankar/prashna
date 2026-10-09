# Performance measurement

Measure Prashna at three separate layers:

1. `Server-Timing: app;dur=...` isolates FastAPI application time.
2. Browser navigation and resource timing captures cold/repeat loads,
   transfers, protocols, paint milestones, and the application-defined
   `prashna-usable` milestone.
3. Structured application logs identify slow or state-changing requests
   without storing credentials, participant identity, session URLs, or Q&A
   content.

`measure.py` records the browser layer plus the server timing, five slowest
resources, transfer sizes, protocol, navigation type, and Cloudflare colo.
Reports are JSON so runs can be compared in CI or retained as release evidence.

Build the frontend and install Chromium before measuring a local server:

```bash
npm run build
uv run playwright install chromium
uv run python performance/measure.py \
  --base-url http://127.0.0.1:8000 \
  --session-code ABC123 \
  --runs 5 \
  --output /tmp/prashna-perf.json
```

For production, save a baseline and compare the same routes after a change:

```bash
uv run python performance/measure.py \
  --base-url https://prashna.sankara.net \
  --session-code ABC123 \
  --budget performance/budgets.json \
  --output /tmp/prashna-before.json

uv run python performance/measure.py \
  --base-url https://prashna.sankara.net \
  --session-code ABC123 \
  --baseline /tmp/prashna-before.json \
  --max-regression-percent 20 \
  --budget performance/budgets.json \
  --output /tmp/prashna-after.json
```

Use repeated samples from the same machine and network. Do not compare one
cold browser run with one warm run or infer browser speed from server timing
alone. Production budgets are intentionally broad enough for normal network
variation; baseline comparison provides the more sensitive release signal.
Every measured page must emit the usable milestone; a fast error or incomplete
boot therefore cannot pass merely because network activity stopped.
With the default five samples, release gates use browser/transfer medians and
application-time p95. Browser p95 remains in every report for diagnosis, but
needs at least 20 samples before it is a useful percentile rather than nearly
the single slowest request.

Optional authenticated measurements read secrets from environment variables
without writing them to reports:

```bash
uv run python performance/measure.py \
  --base-url https://prashna.sankara.net \
  --session-code ABC123 \
  --moderator-key-env PRASHNA_PERF_MOD_KEY \
  --route moderator=/m/ABC123
```

For an admin page, pass both `--admin-username-env` and
`--admin-password-env`. Never put credentials or moderator keys directly in a
command, report, or committed file.

## Interpret high variance

Do not infer browser performance from application timing or one public request.
When `Server-Timing` stays low but navigation varies, separate these fault
domains:

- client access network and ISP;
- client-to-Cloudflare ingress routing;
- Cloudflare edge and cache behavior;
- Cloudflare-to-Hetzner origin routing; and
- nginx, FastAPI, SQLite, and host capacity.

Capture several successful and failed samples from the same machine and
network. Record UTC time, client ISP/ASN, `CF-RAY`, `CF-Cache-Status`, negotiated
protocol, cURL phase timings, and MTR/traceroute output. Compare against an
unrelated control host during the same interval.

For Cloudflare routing, compare `https://prashna.sankara.net/cdn-cgi/trace`
with Cloudflare control endpoints from the same connection. Different `colo`
values are possible because anycast selection is destination-prefix-specific;
the value is not simply the geographically nearest data center. A different
colo explains the path selection, but does not by itself prove the cause of
latency variance. Correlate it with timestamped timings, Ray IDs, packet loss,
and path traces.

There is no zone setting that pins client ingress to a particular Cloudflare
colo. Argo Smart Routing affects the edge-to-origin path, not client-to-edge
selection. Keep the hostname proxied unless collected evidence shows the proxy
itself is the regression. The nginx visitor-IP and HTTP/2 setup and the
HTML-shell cache rule are described in
[`deploy/README.md`](../deploy/README.md#cloudflare-visitor-ip-and-http2).

## Release verification

For a performance-sensitive release:

1. Run lint and the full automated suite.
2. Save a pre-release JSON report when practical.
3. Deploy and verify the intended immutable image revision.
4. Check container health, `/api/admin/status`, and a direct static page.
5. Repeat the browser measurement from the same location and network.
6. Confirm HTTP/2 or HTTP/3, immutable compressed assets, page-shell cache
   behavior, API `no-store`, and `Server-Timing`.

Five-run gates use browser and transfer medians plus application p95. Retain
browser p95 for diagnosis, but use at least 20 samples before treating it as a
meaningful tail percentile.
