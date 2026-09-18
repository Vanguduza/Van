#!/usr/bin/env bash
set -euo pipefail

RULES_V4="${VAN_ORACLE_RULES_V4:-/etc/iptables/rules.v4}"
ADMIN_CIDRS="${VAN_ADMIN_CIDRS:-10.0.0.123/32,10.0.0.184/32}"
PUBLIC_HOST="${VAN_PUBLIC_HOST:-}"
VERIFY_ONLY=0
[[ "${1:-}" == "--verify" ]] && VERIFY_ONLY=1

die() { echo "ORACLE_IMAGE_FIREWALL_RED: $*" >&2; exit 1; }
[[ "$(id -u)" == "0" ]] || die "run as root"
[[ -f "$RULES_V4" ]] || die "$RULES_V4 missing"
grep -q "iptables configuration for Oracle Cloud Infrastructure" "$RULES_V4" || die "not an OCI cloud-image rules file"
command -v iptables >/dev/null 2>&1 || die "iptables missing"

IFS=',' read -r -a CIDRS <<< "$ADMIN_CIDRS"
(( ${#CIDRS[@]} >= 2 )) || die "at least two admin /32 CIDRs required"
for cidr in "${CIDRS[@]}"; do
  [[ "$cidr" =~ ^10\.0\.[0-9]{1,3}\.[0-9]{1,3}/32$ ]] || die "invalid admin CIDR: $cidr"
done

if (( ! VERIFY_ONLY )); then
  [[ -f "${RULES_V4}.van-original" ]] || cp -a "$RULES_V4" "${RULES_V4}.van-original"
  python3 - "$RULES_V4" "$ADMIN_CIDRS" "$PUBLIC_HOST" <<'PY'
import os, pathlib, re, sys, tempfile
path = pathlib.Path(sys.argv[1])
cidrs = [x for x in sys.argv[2].split(",") if x]
public = bool(sys.argv[3])
lines = path.read_text(encoding="utf-8").splitlines()
out = []
inserted = False
global_ssh = re.compile(r"^-A INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT$")
for line in lines:
    if "VAN_TRADING_MANAGED" in line:
        continue
    if global_ssh.match(line):
        continue
    if not inserted and line == "-A INPUT -j REJECT --reject-with icmp-host-prohibited":
        for cidr in cidrs:
            out.append(f'-A INPUT -s {cidr} -p tcp -m state --state NEW -m tcp --dport 22 -m comment --comment "VAN_TRADING_MANAGED admin-ssh" -j ACCEPT')
            out.append(f'-A INPUT -s {cidr} -p tcp -m state --state NEW -m tcp --dport 9133 -m comment --comment "VAN_TRADING_MANAGED commander" -j ACCEPT')
        if public:
            out.append('-A INPUT -p tcp -m state --state NEW -m tcp --dport 80 -m comment --comment "VAN_TRADING_MANAGED public-http" -j ACCEPT')
            out.append('-A INPUT -p tcp -m state --state NEW -m tcp --dport 443 -m comment --comment "VAN_TRADING_MANAGED public-https" -j ACCEPT')
        inserted = True
    out.append(line)
if not inserted:
    raise SystemExit("OCI INPUT reject anchor missing")
st = path.stat()
fd, tmp = tempfile.mkstemp(prefix=".rules.v4.van.", dir=str(path.parent), text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, st.st_mode & 0o777)
    os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, path)
finally:
    if os.path.exists(tmp):
        os.unlink(tmp)
PY

  add_live() {
    if ! iptables -C INPUT "$@" 2>/dev/null; then
      iptables -I INPUT 4 "$@"
    fi
  }
  for cidr in "${CIDRS[@]}"; do
    add_live -s "$cidr" -p tcp -m state --state NEW -m tcp --dport 22 -m comment --comment "VAN_TRADING_MANAGED admin-ssh" -j ACCEPT
    add_live -s "$cidr" -p tcp -m state --state NEW -m tcp --dport 9133 -m comment --comment "VAN_TRADING_MANAGED commander" -j ACCEPT
  done
  if [[ -n "$PUBLIC_HOST" ]]; then
    add_live -p tcp -m state --state NEW -m tcp --dport 80 -m comment --comment "VAN_TRADING_MANAGED public-http" -j ACCEPT
    add_live -p tcp -m state --state NEW -m tcp --dport 443 -m comment --comment "VAN_TRADING_MANAGED public-https" -j ACCEPT
  fi
  while iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT 2>/dev/null; do
    iptables -D INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT
  done
fi

for cidr in "${CIDRS[@]}"; do
  iptables -C INPUT -s "$cidr" -p tcp -m state --state NEW -m tcp --dport 22 -m comment --comment "VAN_TRADING_MANAGED admin-ssh" -j ACCEPT >/dev/null 2>&1 || die "live SSH rule missing for $cidr"
  iptables -C INPUT -s "$cidr" -p tcp -m state --state NEW -m tcp --dport 9133 -m comment --comment "VAN_TRADING_MANAGED commander" -j ACCEPT >/dev/null 2>&1 || die "live Commander rule missing for $cidr"
  grep -Fq -- "-A INPUT -s $cidr -p tcp -m state --state NEW -m tcp --dport 22 " "$RULES_V4" || die "persistent SSH rule missing for $cidr"
  grep -Fq -- "-A INPUT -s $cidr -p tcp -m state --state NEW -m tcp --dport 9133 " "$RULES_V4" || die "persistent Commander rule missing for $cidr"
done

if iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT 2>/dev/null; then
  die "global SSH allow still present"
fi
if grep -Eq '^-A INPUT -p tcp -m state --state NEW -m tcp --dport 22 -j ACCEPT$' "$RULES_V4"; then
  die "persistent global SSH allow still present"
fi
if [[ -n "$PUBLIC_HOST" ]]; then
  iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 80 -m comment --comment "VAN_TRADING_MANAGED public-http" -j ACCEPT >/dev/null 2>&1 || die "live public rule missing for 80"
  iptables -C INPUT -p tcp -m state --state NEW -m tcp --dport 443 -m comment --comment "VAN_TRADING_MANAGED public-https" -j ACCEPT >/dev/null 2>&1 || die "live public rule missing for 443"
fi

reject_line="$(iptables -L INPUT --line-numbers -n | awk '$2=="REJECT"{print $1; exit}')"
[[ -n "$reject_line" ]] || die "OCI reject rule missing"
for cidr in "${CIDRS[@]}"; do
  src="${cidr%/32}"
  rule_line="$(iptables -L INPUT --line-numbers -n | awk -v s="$src" '$2=="ACCEPT" && $5==s && $9=="dpt:9133"{print $1; exit}')"
  [[ -n "$rule_line" && "$rule_line" -lt "$reject_line" ]] || die "Commander rule for $cidr is not before OCI reject"
done

echo "ORACLE_IMAGE_FIREWALL_GREEN"
