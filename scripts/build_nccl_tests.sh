#!/usr/bin/env bash
# Reconstructed targeted build; CUDA/NCCL/OpenMPI must already be installed.
set -euo pipefail
NCCL_TESTS_DIR=${NCCL_TESTS_DIR:-$HOME/nccl-tests-softroce}
CUDA_HOME=${CUDA_HOME:-/usr/local/cuda}
MPI_HOME=${MPI_HOME:-/usr/lib/x86_64-linux-gnu/openmpi}
revision=afd59abab774a6a4b492eb344bd0c845a0b7bb4d
if [[ -e $NCCL_TESTS_DIR ]]; then
  echo 'Choose an unused NCCL_TESTS_DIR; this script does not overwrite an existing checkout.' >&2
  exit 1
fi
git clone https://github.com/NVIDIA/nccl-tests.git "$NCCL_TESTS_DIR"
git -C "$NCCL_TESTS_DIR" checkout --detach "$revision"
NCCL_TESTS_DIR=$(cd "$NCCL_TESTS_DIR" && pwd)
# Request only the collective used here, bypassing unrelated GIN targets.
make -C "$NCCL_TESTS_DIR/src" "$NCCL_TESTS_DIR/build/all_reduce_perf" \
  BUILDDIR="$NCCL_TESTS_DIR/build" MPI=1 MPI_HOME="$MPI_HOME" \
  CUDA_HOME="$CUDA_HOME" -j "${JOBS:-4}"
test -x "$NCCL_TESTS_DIR/build/all_reduce_perf"
