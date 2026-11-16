# Reproducing the two-node lab

**The original five-stage experiment was completed:** environment installation, rxe/GID setup, connectivity and packet capture, RDMA/TCP benchmarks, and NCCL AllReduce over both RDMA and Socket. The archived logs contain the results; the optional 4-QP scan's failure is retained and documented.

This guide and its helper scripts were assembled during publication from those commands and notes. Offline parsing, real-log tests, plotting, shell syntax, and launcher command construction were checked locally. The exact helper versions have not been used to repeat the cloud experiment. A future two-node run would validate these new helpers, rather than complete an outstanding stage of the original experiment. The numbered sections below organize setup and execution for readers; cleanup is listed separately at the end.

## 1. Prepare two Linux VMs

Use two Ubuntu VMs with private-network connectivity and permission to load `rdma_rxe`. For NCCL, each needs one supported NVIDIA GPU, a working driver/CUDA toolchain, matching NCCL/OpenMPI, and the same executable path. Container instances without the required kernel/module access are insufficient for this setup.

Allow the two **private peer addresses** to communicate over TCP/UDP. The lab used a private-subnet firewall rule; restricting the source to the two peers is sufficient. Relevant ports include UDP 4791 (RoCEv2), TCP 18515 (default verbs/perftest setup), TCP 5201 (iperf3), SSH, and dynamic MPI/NCCL setup ports. Ping success alone does not demonstrate RDMA reachability. Check RDMA-CM port requirements for your installation as well.

On both nodes:

```bash
git clone https://github.com/sxwangsxwang1/softroce-rdma-nccl-lab.git
cd softroce-rdma-nccl-lab
bash scripts/install_rdma.sh
NIC=ens3 bash scripts/setup_rxe.sh
```

Replace `ens3` with the actual private interface. Select the **RoCE v2 IPv4-mapped GID** matching that interface; the archived session used index 1, but it can differ. Record both `ip -d link show` and `ibv_devinfo -v`; RDMA active MTU and Ethernet MTU are distinct.

Set the following on each node, adapting the paths/values:

```bash
export NIC=ens3 RXE=rxe0 GIDX=1
export NODE_A_IP=10.0.0.163 NODE_B_IP=10.0.0.103
export RUN_DIR="$PWD/runs/manual-01"
mkdir -p "$RUN_DIR"
uname -a > "$RUN_DIR/kernel.txt"
ip -d link show dev "$NIC" > "$RUN_DIR/nic.txt"
ibv_devinfo -v -d "$RXE" > "$RUN_DIR/ibv_devinfo.txt"
dpkg-query -W rdma-core perftest libibverbs1 > "$RUN_DIR/packages-rdma.txt"
```

`runs/` is ignored by Git. Use a new directory for every trial; the helpers otherwise overwrite same-named logs. They record the command and exit status alongside combined stdout/stderr.

## 2. Check connectivity and capture traffic

For each test, start node A's server first, then run node B's client. Servers exit after one session and must be restarted for every client invocation.

```bash
# Node A
LOCAL_IP="$NODE_A_IP" bash scripts/run_perftest.sh server rping
# Node B
bash scripts/run_perftest.sh client rping "$NODE_A_IP"

# Node A: start a new server
bash scripts/run_perftest.sh server pingpong
# Node B
bash scripts/run_perftest.sh client pingpong "$NODE_A_IP"
```

The pingpong helper explicitly uses 4096-byte messages, 1000 iterations, a 1024-byte path MTU, and `-g` for GID selection. The expected total is 8,192,000 bytes, counting both directions.

During a connectivity run, capture from a separate node A terminal:

```bash
sudo tcpdump -i "$NIC" -nn 'udp dst port 4791' -c 200 -w "$RUN_DIR/roce_v2.pcap"
tcpdump -nn -r "$RUN_DIR/roce_v2.pcap" > "$RUN_DIR/roce_v2_packets.txt"
```

For full decode, open the capture in Wireshark and inspect the InfiniBand BTH under UDP. Save captures under the same trial identifier as their timing logs if making packet-to-benchmark claims.

## 3. Run RDMA microbenchmarks and TCP baselines

Use the following pattern for each test name:

```bash
# Node A
bash scripts/run_perftest.sh server write-bw
# Node B
bash scripts/run_perftest.sh client write-bw "$NODE_A_IP"
```

Repeat with `write-lat`, `write-bw-q4`, `tcp1`, and `tcp4`, starting a fresh server each time. The scans use the installed perftest defaults plus the explicit recorded flags. Check the printed headers for the resulting depths and iteration counts; the archived version used 5000 Write bandwidth iterations and 1000 latency iterations per size. The 4-QP scan showed 20000 aggregate iterations per row and failed at 1 MiB. A new run may behave differently; preserve all errors and exit codes.

For CPU sampling, use a separate fixed-size, 30-second bandwidth run:

```bash
# Node A: server first
bash scripts/run_perftest.sh server write-bw-duration
# Node B, separate terminal before starting its client
top -b -d 1 -n 35 > "$RUN_DIR/top-full.txt"
# Node B, another terminal
bash scripts/run_perftest.sh client write-bw-duration "$NODE_A_IP"
```

Collect the full `top` output on node A as well. For stronger attribution in a new study, capture timestamped per-core/per-process data, record CPU affinity and NIC offload settings, repeat trials, and retain the matching bandwidth output. Sampling order alone does not align the two nodes.

## 4. Prepare CUDA, NCCL, MPI, and SSH

The archived working combination was driver 570.195.03, CUDA toolkit 12.8, NCCL `2.32.6-1+cuda12.9`, and OpenMPI 4.1.6. This records one successful combination, not a general compatibility guarantee. Install a compatible CUDA/NCCL build using [NVIDIA's instructions](https://docs.nvidia.com/deeplearning/nccl/install-guide/index.html); do not accept an unrelated newer CUDA build solely because apt selects it by default.

For the historical package choice, after configuring the appropriate NVIDIA repository:

```bash
sudo apt-get install -y --allow-downgrades \
  libnccl2=2.32.6-1+cuda12.9 libnccl-dev=2.32.6-1+cuda12.9 \
  openmpi-bin libopenmpi-dev
nvidia-smi
nvcc --version
dpkg-query -W libnccl2 libnccl-dev openmpi-bin
```

Historical package availability may change. On both nodes, build the same pinned source revision at the same absolute path:

```bash
export NCCL_TESTS_DIR="$HOME/nccl-tests-softroce"
bash scripts/build_nccl_tests.sh
```

The helper requests only `all_reduce_perf`, avoiding the unrelated GIN targets that failed during the original broad build. It deliberately refuses to overwrite an existing checkout. This targeted path is a publication-time reconstruction, not a historical build success claim. [Pinned upstream Makefile](https://github.com/NVIDIA/nccl-tests/blob/afd59abab774a6a4b492eb344bd0c845a0b7bb4d/src/Makefile)

Configure SSH from the launch node to both peer addresses, including the launch node itself. Verify host keys and test `ssh NODE_A_IP hostname` and `ssh NODE_B_IP hostname`. Both nodes need the same user/path and access to CUDA/NCCL libraries. Check inherited NCCL environment variables and `nccl.conf` before controlled comparisons; the helper does not clear every possible system setting.

## 5. Run NCCL AllReduce twice

From node A:

```bash
NIC=ens3 bash scripts/run_nccl.sh rdma "$NODE_A_IP" "$NODE_B_IP"
NIC=ens3 bash scripts/run_nccl.sh socket "$NODE_A_IP" "$NODE_B_IP"
```

Both runs use 2 MPI ranks, 1 GPU/rank, sizes 8 B–256 MiB, and factor-of-two steps. The RDMA run selects `rxe0`/GID index and enables IB; the control disables IB. Both set `NCCL_NET_GDR_LEVEL=0` to disable GPUDirect RDMA. [NCCL environment reference](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html)

Confirm all three conditions in the resulting logs:

- Both ranks select `Using network IB` and data channels `via NET/IB/0` in the RDMA run; the control selects Socket.
- Every size and both buffer modes report zero validation errors, with `Out of bounds values : 0 OK` and a test conclusion.
- The runtime identifies the intended NCCL version and shows GPUDirect RDMA disabled.

The combined output may interleave debug messages and numeric rows, as the historical run did. For new measurements, NCCL's per-process `NCCL_DEBUG_FILE` facility can keep debug output separate; ensure its parent directory exists on every node. The committed parser is designed to recover the specific historical log format, not act as a universal importer for future versions.

## 6. Finish the run

Collect both nodes' outputs, command files, final package versions, source commit, and exit codes. Keep independent trials in separate directories. Remove the software device with `sudo rdma link delete rxe0` when done. Release cloud resources through the provider when the experiment is complete; deletion status cannot be determined from this repository's logs.
