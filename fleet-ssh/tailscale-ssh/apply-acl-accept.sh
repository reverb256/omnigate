#!/bin/bash
# Minimal tailnet policy edit: ssh rule check -> accept (portal-free once a key exists).
# The policy layer needs a credential; see README (one-time mint in admin console).
# Usage: TS_API_KEY=tskey-api-... ./apply-acl-accept.sh
#    or: write the key to ~/.config/tailscale/api-key (600) and run without env.
set -euo pipefail
KEY="${TS_API_KEY:-}"
if [ -z "$KEY" ] && [ -f "$HOME/.config/tailscale/api-key" ]; then
  KEY="$(tr -d '[:space:]' < "$HOME/.config/tailscale/api-key")"
fi
[ -z "$KEY" ] && { echo "NO-KEY: set TS_API_KEY or write ~/.config/tailscale/api-key"; exit 2; }
API="https://api.tailscale.com/api/v2/tailnet/-/acl"
BAK="/tmp/tailnet-acl.backup.$(date +%Y%m%d-%H%M%S).hujson"
curl -sf -m 20 -u "$KEY:" "$API" -o "$BAK" || { echo "GET-FAILED: key invalid/expired or network"; exit 1; }
echo "backup saved: $BAK"
python3 - "$BAK" > /tmp/tailnet-acl.new.json <<'PY'
import json, re, sys
raw = open(sys.argv[1]).read()
try:
    pol = json.loads(raw)
except json.JSONDecodeError:
    pol = json.loads(re.sub(r'//[^\n]*', '', raw))
changed = 0
for rule in pol.get("ssh", []):
    if rule.get("action") == "check":
        rule["action"] = "accept"
        rule.pop("checkPeriod", None)
        changed += 1
json.dump(pol, sys.stdout, indent=2)
print("", file=sys.stdout)
sys.stderr.write("ssh rules flipped check->accept: %d\n" % changed)
PY
echo "-- diff preview (ssh section):"
python3 -c "
import json
old = open('$BAK').read()
new = open('/tmp/tailnet-acl.new.json').read()
import re
def ssh_sec(t):
    try: p = json.loads(t)
    except Exception: p = json.loads(re.sub(r'//[^\n]*','',t))
    return json.dumps(p.get('ssh',[]), indent=2)
print('BEFORE:', ssh_sec(old)[:400])
print('AFTER :', ssh_sec(new)[:400])
"
curl -sf -m 20 -u "$KEY:" -H "Content-Type: application/json" --data-binary @/tmp/tailnet-acl.new.json "$API" -o /tmp/tailnet-acl.put.json && echo "PUT-OK" || { echo "PUT-FAILED"; exit 1; }
curl -sf -m 20 -u "$KEY:" "$API" -o /tmp/tailnet-acl.verify.json && grep -q '"accept"' /tmp/tailnet-acl.verify.json && echo "VERIFY-OK: accept rules present" || echo "VERIFY-UNSURE: check manually"
echo "rollback: PUT the saved backup back to $API, or run this script is idempotent"
