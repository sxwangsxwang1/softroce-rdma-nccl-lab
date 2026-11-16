#!/usr/bin/env bash
# Reconstructed launcher. Requires matching binary paths and SSH access on both nodes.
set -euo pipefail
if [[ $# != 3 || ( $1 != rdma && $1 != socket ) ]]; then
  echo "Usage: NIC=ens3 $0 rdma|socket NODE_A_IP NODE_B_IP" >&2
  exit 2
fi
: "${NIC:?Set NIC to the private-network interface}"
transport=$1
node_a=$2
node_b=$3
RXE=${RXE:-rxe0}
GIDX=${GIDX:-1}
NCCL_TESTS_DIR=${NCCL_TESTS_DIR:-$HOME/nccl-tests-softroce}
RUN_DIR=${RUN_DIR:-runs/$(date -u +%Y%m%dT%H%M%SZ)}
test -x "$NCCL_TESTS_DIR/build/all_reduce_perf"
mkdir -p "$RUN_DIR"
command=(mpirun -np 2 -H "$node_a:1,$node_b:1"
  --mca btl_tcp_if_include "$NIC" --mca oob_tcp_if_include "$NIC"
  -x NCCL_DEBUG=INFO -x NCCL_DEBUG_SUBSYS=INIT,NET
  -x "NCCL_SOCKET_IFNAME=$NIC" -x NCCL_NET_GDR_LEVEL=0)
if [[ $transport == rdma ]]; then
  command+=(-x NCCL_IB_DISABLE=0 -x "NCCL_IB_HCA=$RXE" -x "NCCL_IB_GID_INDEX=$GIDX")
else
  command+=(-x NCCL_IB_DISABLE=1)
fi
command+=("$NCCL_TESTS_DIR/build/all_reduce_perf" -b 8 -e 256M -f 2 -g 1)
log="$RUN_DIR/nccl_allreduce_${transport}.txt"
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
