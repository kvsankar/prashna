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

## Network-path incidents

If browser navigation is slow while `Server-Timing` remains low, test the
public path separately from the origin before tuning the application. Capture
several samples rather than relying on one request, compare HTTP/1.1 and
HTTP/2, and check packet loss to both the origin and unrelated control hosts.

On 2026-08-16, a slow episode showed 55% packet loss from the measurement
network to the Hetzner origin and public requests taking up to tens of seconds,
while the origin interface reported no errors or drops, host load was low, and
the application completed the same requests in milliseconds. Control requests
to unrelated public services had no packet loss. That combination identifies
the direct Internet route to the Finland origin as the dominant fault domain,
not FastAPI, SQLite, nginx processing, or HTTP/2.

For `prashna.sankara.net`, the supported mitigation for an unstable direct
client-to-Hetzner route is Cloudflare's HTTP proxy. Before changing the DNS
record from DNS-only to proxied, run:

```bash
deploy/prepare-cloudflare-proxy.sh
```

The helper downloads and validates Cloudflare's published IPv4 and IPv6
ranges, configures nginx's real-IP module to trust `CF-Connecting-IP` only
from those networks, takes timestamped backups, validates nginx, and reloads
only on success. This preserves per-visitor rate-limit buckets with the
existing `PRASHNA_TRUSTED_PROXY_HOPS=1` setting. Re-run it periodically to
refresh Cloudflare's address ranges.

After proxying the DNS record, verify that public DNS returns Cloudflare
addresses, responses include `CF-Ray`, the landing/moderator/projector flows
and WebSockets work, and nginx access logs retain distinct visitor addresses.
Changing the record back to DNS-only is the traffic rollback; the nginx
real-IP configuration is safe to leave installed because it trusts the
Cloudflare header only when the connection source is a published Cloudflare
network.

### 2026-08-16 Cloudflare cutover

The `prashna` DNS record was changed from DNS-only to proxied after nginx was
prepared. Public resolvers returned Cloudflare anycast addresses, responses
included a Singapore `CF-Ray`, all landing/participant/moderator/projector and
session API smoke requests returned HTTP 200, and a secure WebSocket connected
and sent successfully through the edge. Production access-log inspection also
confirmed that nginx restored the visitor address instead of recording a
shared Cloudflare address. Fingerprinted assets changed from `MISS` to `HIT`
while retaining their immutable cache policy.

Eight bounded API samples through the edge all succeeded with a median around
0.79 seconds. A warmed landing-page browser sample completed five of six loads
with a 1.37-second successful median; one 15-second timeout remained. Control
requests during the same interval also showed multi-second TLS stalls and one
failure against Google, and packet loss appeared against Cloudflare, Google,
and the Hetzner origin. The remaining tail was therefore attributable to the
measurement workstation's access link rather than Prashna or the
Cloudflare-to-origin path. Keep HTTP/3 enabled: disabling QUIC on the same
workstation increased the successful landing median to 4.38 seconds and did
not remove the one-in-six timeout.

Recursive resolvers may continue returning the former origin address until
their pre-cutover TTL expires. During that window, use an explicit resolver or
host override for edge verification; do not mistake a cached DNS answer for a
failed Cloudflare change.

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
resource inspection, or application timing. Five-run release gates use browser
medians and application p95 while retaining browser p95s in the report. Use at
least 20 samples when interpreting a browser p95. Network variance means a
single public request is not useful release evidence.
