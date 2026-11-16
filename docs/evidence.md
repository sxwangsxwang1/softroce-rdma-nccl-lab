# Evidence, provenance, and publication corrections

The public report was checked against 43 text logs and one PCAP. Original logs are kept unmodified, including failed builds and the interrupted 4-QP run. Derived tables and figures were produced after the experiment. The setup/run scripts were reconstructed from the notes and tool interfaces; they have not been rerun on the original GPU VMs.

## What each artifact supports

| Claim | Evidence | Limit |
|---|---|---|
| The software RDMA devices were active | Both nodes' `ibv_devinfo_*.txt`, `gids_*.txt`, and `env_*.txt` | Does not record Ethernet MTU or offload configuration |
| RDMA CM and RC exchanges completed | `rping_*` and `rc_pingpong_*` | Connectivity runs are distinct from benchmark scans |
| RoCEv2 packets traversed the private interface | 200-frame PCAP, UDP 4791 and BTH structure | Separate capture session; not a trace of each perftest/NCCL run |
| NCCL selected rxe as its data transport | Both ranks' `Using network IB`, `rxe0:1/RoCE`, and `via NET/IB/0` | TCP still appears for bootstrap and coordination |
| NCCL used host staging | `GPU Direct RDMA Disabled` in the successful logs | No GPUDirect RDMA performance claim |
| Both collective scans passed validation | Zero errors for all sizes and both modes; `0 OK` and test conclusion | One scan per transport; no independent repetitions |
| Software RDMA consumed CPU time | Aggregate `top` observations on both nodes | No process attribution, timestamps, synchronized windows, or archived associated duration-mode throughput |

## Corrections to the original handoff report

1. **RC pingpong size and command.** The output's `8192000 bytes` is the total for `message_size × iterations × 2`. At 1000 iterations, the message size is 4096 B. Its reported 327.03 µs/iteration is a round trip. The matching rdma-core utility uses `-g` for GID index, while perftest uses `-x`. The original report's `-x 1 -s 8192000` command does not describe the archived result. [rdma-core v50.0 source](https://github.com/linux-rdma/rdma-core/blob/v50.0/libibverbs/examples/rc_pingpong.c)

2. **4-QP completion status.** The interrupted 1 MiB row has `status 5`, which maps to `IBV_WC_WR_FLUSH_ERR`. It is not the enumeration value for retry exhaustion (`IBV_WC_RETRY_EXC_ERR`, 12). A flush completion can be secondary to another error; the initiating cause is not established by the saved logs. [Status enumeration](https://github.com/linux-rdma/rdma-core/blob/v50.0/libibverbs/verbs.h#L461-L474)

3. **CPU attribution and bottlenecks.** Total `us`/`sy`/`si` percentages are machine-level measurements. Without per-process/per-core data and synchronized timestamps they cannot establish “1.9 cores of polling plus 0.65 cores of rxe,” nor a unique whole-machine CPU ceiling. Nice time and CPU steal are visible in the samples. Higher software overhead is a plausible contributor; its exact causal share was not isolated.

4. **NCCL versions.** Both early package snapshots show `2.32.6-1+cuda13.5`. Both `apt_nccl_swap_*` logs record replacement with `2.32.6-1+cuda12.9`, and the successful NCCL logs identify that final build. The final runtime version takes precedence over the earlier snapshot. The original CUDA-driver failure is described in the operator's notes; a raw log of that failed invocation is not present.

5. **Size, bandwidth, and latency conventions.** A 131072-byte message is 128 KiB. perftest and iperf3 here report Gb/s; NCCL reports GB/s. The NCCL tool's scan average mixes message sizes and both buffer modes. At 256 MiB, RDMA out-of-place/in-place busbw is 0.20/0.19 GB/s and Socket is 0.57/0.58 GB/s. Hardware RoCE latency and the share attributable to software versus virtualization were not measured.

6. **Evidence continuity.** The PCAP's destination QPs are `0x13` and `0x14`; the saved pingpong timing logs identify `0x12` and `0x13`. These are separate sessions. The capture supports protocol validation within the lab, without establishing packet-level provenance for the saved timing run. Its 1040-byte UDP data payloads are consistent with a 1024-byte RDMA payload plus headers/trailer, despite `ibv_devinfo` reporting active MTU 4096. The pingpong utility defaults to a 1024-byte path MTU; the published reconstruction makes that explicit.

7. **Queue depth.** The Write scan reports TX depth 128 and the Write latency scan depth 1. Pingpong also differs in verbs operation, message size, and synchronization. Its approximately 200 Mbit/s cannot be compared with Write's peak to attribute the entire difference solely to queue depth.

8. **Build outcome.** Both nccl-tests builds ended with `make` errors in optional GIN targets, while the AllReduce binary was linked and then executed successfully. The reconstructed build requests only the AllReduce target at the logged source revision; that new build path was not exercised on the historical VMs.

## Capture inspection

`analysis/summarize.py` reads the PCAP directly, validates Ethernet/IPv4/unfragmented UDP framing and destination port, and counts BTH opcode bytes. This is a focused header inspection, not a full InfiniBand conformance or ICRC validator.

| BTH opcode | RC operation | Frames |
|---|---|---:|
| `0x00` | SEND First | 40 |
| `0x01` | SEND Middle | 80 |
| `0x02` | SEND Last | 40 |
| `0x11` | Acknowledge | 40 |

Both private-address directions contain 100 frames. The capture spans about 7.041 ms. The file contains local MAC addresses and private IPv4 endpoints; no public endpoints occur in its packet headers.

## Deliberately absent claims

There are no measurements of hardware RDMA, PFC/ECN/DCQCN behavior, switch congestion, RDMA Read/Send bandwidth scans, more than two nodes, or GPUDirect RDMA performance. Cloud prices, costs, and VM deletion status are not inferred from performance logs.
