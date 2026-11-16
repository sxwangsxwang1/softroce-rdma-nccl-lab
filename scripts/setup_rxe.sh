#!/usr/bin/env bash
# Reconstructed after the experiment. NIC must be the private-network interface.
set -euo pipefail
: "${NIC:?Set NIC to the private-network interface, e.g. NIC=ens3}"
RXE=${RXE:-rxe0}
ip link show dev "$NIC" >/dev/null
sudo modprobe rdma_rxe
if [[ -e /sys/class/infiniband/$RXE ]]; then
  rdma link show "$RXE/1"
  echo 'Device already exists. Verify its netdev matches NIC before continuing.'
else
  sudo rdma link add "$RXE" type rxe netdev "$NIC"
fi
ibv_devinfo -v -d "$RXE"
ip -d link show dev "$NIC"
for path in /sys/class/infiniband/"$RXE"/ports/1/gids/*; do
  index=${path##*/}
  gid=$(cat "$path")
  type=$(cat "/sys/class/infiniband/$RXE/ports/1/gid_attrs/types/$index")
  if [[ $gid != 0000:0000:0000:0000:0000:0000:0000:0000 ]]; then
    printf 'idx=%s type=%s gid=%s\n' "$index" "$type" "$gid"
  fi
done
echo 'Choose the RoCE v2 IPv4-mapped GID for this NIC; do not assume its index is 1.'
