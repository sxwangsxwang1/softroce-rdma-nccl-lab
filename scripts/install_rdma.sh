#!/usr/bin/env bash
# Reconstructed after the experiment. Run on each Ubuntu VM.
set -euo pipefail
if [[ $(uname -s) != Linux ]]; then
  echo 'This setup requires Linux VMs; offline analysis also runs on macOS.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y rdma-core ibverbs-utils rdmacm-utils perftest iproute2 \
  iperf3 tcpdump git build-essential
if ! sudo modprobe rdma_rxe; then
  echo "Install linux-modules-extra-$(uname -r), or boot a compatible generic kernel, then retry." >&2
  exit 1
fi
