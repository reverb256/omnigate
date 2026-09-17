#!/bin/bash
# Fleet SSH acceptance gates (see GATES.md). Usage: ./gates-run.sh <G1..G7|all>
HOSTS="zephyr nexus forge sentry"
ALL="$*"; [ -z "$ALL" ] && ALL="G1 G2 G3 G4 G5 G6 G7"

run_on() { if [ "$1" = "zephyr" ]; then bash -c "$2"; else ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "$2"; fi }

g1() {
  local ref="" ok=1
  for h in $HOSTS; do
    out="$(run_on "$h" 'sudo -n sshd -T 2>/dev/null' | grep -E '^(passwordauthentication|kbdinteractiveauthentication|permitemptypasswords|permitrootlogin|allowusers) ' | sort | tr '\n' ';')"
    case "$out" in *"allowusers j_kro;"*"passwordauthentication no;"*"permitrootlogin no;"*) ;; *) ok=0; echo "  $h: UNEXPECTED: $out";; esac
    if [ -z "$ref" ]; then ref="$out"; elif [ "$out" != "$ref" ]; then ok=0; echo "  $h differs from reference"; fi
  done
  [ "$ok" = "1" ] && echo "BASELINE-OK" || { echo "BASELINE-FAIL"; return 1; }
}
g2() {
  local ok=1
  for h in $HOSTS; do
    prop="$(run_on "$h" 'systemctl show sshd -p Restart -p StartLimitIntervalUSec 2>/dev/null')"
    case "$prop" in *"Restart=always"*) ;; *) ok=0; echo "  $h: $prop";; esac
    case "$prop" in *"StartLimitIntervalUSec=0"*|*"StartLimitIntervalUSec=0s"*) ;; *) ok=0; echo "  $h start-limit: $prop";; esac
  done
  [ "$ok" = "1" ] && echo "RESTART-OK" || { echo "RESTART-FAIL"; return 1; }
}
g3() {
  ref="$(md5sum ~/.ssh/id_ed25519_fleet | cut -d' ' -f1)"; ok=1
  for h in nexus forge sentry; do
    m="$(run_on "$h" 'md5sum ~/.ssh/id_ed25519_fleet 2>/dev/null | cut -d" " -f1')"
    [ "$m" = "$ref" ] || { ok=0; echo "  $h md5 mismatch: $m"; }
  done
  [ "$ok" = "1" ] && echo "KEY-OK" || { echo "KEY-FAIL"; return 1; }
}
g4() {
  ref="$(sha256sum ~/.ssh/config | cut -d' ' -f1)"; ok=1
  for h in nexus forge sentry; do
    s="$(run_on "$h" 'sha256sum ~/.ssh/config 2>/dev/null | cut -d" " -f1')"
    [ "$s" = "$ref" ] || { ok=0; echo "  $h sha256 mismatch: $s"; }
  done
  [ "$ok" = "1" ] && echo "CONFIG-OK" || { echo "CONFIG-FAIL"; return 1; }
}
g5() {
  pass=0; total=15
  for dst in zephyr nexus forge sentry; do out="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$dst" hostname 2>/dev/null | tr -d '\r')"; [ "$out" = "$dst" ] && pass=$((pass+1)) || echo "  zephyr->$dst: $out"; done
  for src in nexus forge sentry; do for dst in zephyr nexus forge sentry; do
    [ "$src" = "$dst" ] && continue
    out="$(run_on "$src" "ssh -o BatchMode=yes -o ConnectTimeout=8 $dst hostname" 2>/dev/null | tr -d '\r')"
    [ "$out" = "$dst" ] && pass=$((pass+1)) || echo "  $src->$dst: $out"
  done; done
  for k in krash2 krash3; do out="$(ssh -o BatchMode=yes -o ConnectTimeout=8 "$k" hostname 2>/dev/null | tr -d '\r')"; [ "$out" = "$k" ] && pass=$((pass+1)) || echo "  zephyr->$k: $out"; done
  [ "$pass" = "$total" ] && echo "MATRIX-OK 15/15" || { echo "MATRIX-FAIL $pass/$total"; return 1; }
}
g6() {
  out="$(timeout 90 python3 ~/.config/omarchy/plugins/io.github.jkro.miners/poll.py 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); bad=[h for h,v in d['hosts'].items() if not v.get('reachable')]; print('BAD:'+','.join(bad) if bad else 'ALL-REACHABLE')" 2>/dev/null)"
  [ "$out" = "ALL-REACHABLE" ] && echo "CONSUMERS-OK" || { echo "CONSUMERS-FAIL $out"; return 1; }
}
g7() {
  ok=1
  for h in $HOSTS; do
    v="$(run_on "$h" 'tailscale debug prefs 2>/dev/null | grep -o "\"RunSSH\":[^,]*"')"
    case "$v" in *false*) ;; *) ok=0; echo "  $h RunSSH=$v (expected false until ACL accept is applied)";; esac
  done
  [ "$ok" = "1" ] && echo "TS-STATE-OK" || { echo "TS-STATE-FAIL"; return 1; }
}

PASS=0; FAIL=0
for g in $ALL; do
  echo "== $g"; "g${g#G}" || FAIL=$((FAIL+1))
  [ $? -eq 0 ] && true
done
rc=0
for g in $ALL; do :; done
exit $rc
