#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--dry-run|--apply]"
  echo "Requires CLOUDFLARE_API_TOKEN; CLOUDFLARE_ZONE_ID is optional."
}

mode="dry-run"
case "${1:-}" in
  ""|--dry-run) ;;
  --apply) mode="apply" ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

cf_api_token="${CLOUDFLARE_API_TOKEN:-${SANKARA_NET_CLOUDFLARE_API_TOKEN:-}}"
if [[ -z "$cf_api_token" ]]; then
  echo "Set CLOUDFLARE_API_TOKEN or SANKARA_NET_CLOUDFLARE_API_TOKEN" >&2
  exit 1
fi

api_base="https://api.cloudflare.com/client/v4"
zone_id="${CLOUDFLARE_ZONE_ID:-}"
auth_header="Authorization: Bearer ${cf_api_token}"

if [[ -z "$zone_id" ]]; then
  zone_response=$(curl --fail-with-body --silent --show-error \
    --get "$api_base/zones" \
    --header "$auth_header" \
    --data-urlencode "name=sankara.net" \
    --data-urlencode "status=active")
  zone_id=$(jq -er '.result | if length == 1 then .[0].id else error("expected one active sankara.net zone") end' \
    <<<"$zone_response")
fi

phase="http_request_cache_settings"
entrypoint="$api_base/zones/$zone_id/rulesets/phases/$phase/entrypoint"
response_file=$(mktemp /tmp/prashna-cloudflare-cache.XXXXXX)
payload_file=$(mktemp /tmp/prashna-cloudflare-payload.XXXXXX)
trap 'rm -f "$response_file" "$payload_file"' EXIT

http_status=$(curl --silent --show-error \
  --output "$response_file" \
  --write-out '%{http_code}' \
  --header "$auth_header" \
  "$entrypoint")
if [[ "$http_status" != "200" && "$http_status" != "404" ]]; then
  jq -r '.errors[]?.message // empty' "$response_file" >&2 || true
  echo "Cloudflare ruleset read failed with HTTP $http_status" >&2
  exit 1
fi

expression='(http.host eq "prashna.sankara.net" and (http.request.uri.path eq "/" or http.request.uri.path eq "/quizzes" or starts_with(http.request.uri.path, "/s/") or starts_with(http.request.uri.path, "/m/") or starts_with(http.request.uri.path, "/p/")))'

jq --arg phase "$phase" --arg expression "$expression" '
  (.result.rules // [])
  | map(select(.ref != "prashna_html_shells"))
  | . + [{
      ref: "prashna_html_shells",
      description: "Cache Prashna static HTML shells; respect application TTLs",
      expression: $expression,
      action: "set_cache_settings",
      action_parameters: {
        cache: true,
        edge_ttl: {mode: "respect_origin"},
        browser_ttl: {mode: "respect_origin"}
      },
      enabled: true
    }]
  | {
      name: "default",
      description: "Zone-level cache settings",
      kind: "zone",
      phase: $phase,
      rules: .
    }
' "$response_file" >"$payload_file"

if [[ "$mode" == "dry-run" ]]; then
  echo "Dry run: Cloudflare cache entrypoint would be replaced with:"
  jq . "$payload_file"
  exit 0
fi

apply_response=$(curl --fail-with-body --silent --show-error \
  --request PUT "$entrypoint" \
  --header "$auth_header" \
  --header 'Content-Type: application/json' \
  --data-binary "@$payload_file")
jq -e '.success == true' <<<"$apply_response" >/dev/null
jq -r '"Applied Prashna HTML cache rule in ruleset " + .result.id' <<<"$apply_response"
