#!/usr/bin/env bash
# Reconstructed commands; each server process handles one session.
set -euo pipefail
if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "Usage: $0 server|client write-bw|write-lat|write-bw-q4|write-bw-duration|pingpong|rping|tcp1|tcp4 [SERVER_IP]" >&2
  exit 2
fi
role=$1
test_name=$2
server_ip=${3:-}
RXE=${RXE:-rxe0}
GIDX=${GIDX:-1}
RUN_DIR=${RUN_DIR:-runs/$(date -u +%Y%m%dT%H%M%SZ)}
[[ $role == server || $role == client ]] || { echo 'Invalid role' >&2; exit 2; }
if [[ $role == client && -z $server_ip ]]; then
  echo 'Client requires SERVER_IP' >&2
  exit 2
fi
case "$test_name" in
  write-bw) command=(ib_write_bw -d "$RXE" -x "$GIDX" -F --report_gbits -a) ;;
  write-lat) command=(ib_write_lat -d "$RXE" -x "$GIDX" -F -a) ;;
  write-bw-q4) command=(ib_write_bw -d "$RXE" -x "$GIDX" -F --report_gbits -a -q 4) ;;
  write-bw-duration) command=(ib_write_bw -d "$RXE" -x "$GIDX" -F --report_gbits -s 65536 -D 30) ;;
  pingpong) command=(ibv_rc_pingpong -d "$RXE" -g "$GIDX" -s 4096 -m 1024 -n 1000) ;;
  rping)
    if [[ $role == server ]]; then
      : "${LOCAL_IP:?Set LOCAL_IP to the server private IPv4 address}"
      command=(rping -s -a "$LOCAL_IP" -v -C 10)
    else
      command=(rping -c -a "$server_ip" -v -C 10)
    fi ;;
  tcp1|tcp4)
    if [[ $role == server ]]; then
      command=(iperf3 -s -1)
    else
      streams=1
      [[ $test_name != tcp4 ]] || streams=4
      command=(iperf3 -c "$server_ip" -t 30 -P "$streams")
    fi ;;
  *) echo "Unknown test: $test_name" >&2; exit 2 ;;
esac
if [[ $role == client && $test_name != rping && $test_name != tcp* ]]; then
  command+=("$server_ip")
fi
mkdir -p "$RUN_DIR"
log="$RUN_DIR/${test_name}_${role}.txt"
printf '%q ' "${command[@]}" > "$log.command"
printf '\n' >> "$log.command"
set +e
"${command[@]}" 2>&1 | tee "$log"
statuses=("${PIPESTATUS[@]}")
set -e
status=${statuses[0]}
[[ $status != 0 ]] || status=${statuses[1]}
printf '%s\n' "$status" > "$log.exitcode"
exit "$status"
