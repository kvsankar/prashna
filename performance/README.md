# Performance measurement

`measure.py` records fresh-profile and repeat-load browser timings, the
application-defined `prashna-usable` milestone, transfer sizes, protocols, the
five slowest resources, and Prashna's `Server-Timing` application duration.
Reports are JSON so runs can be compared in CI or kept as release evidence.

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
