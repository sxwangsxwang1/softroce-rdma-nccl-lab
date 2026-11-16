# Soft-RoCE RDMA 与双机 NCCL AllReduce 实验报告

实验日期：2026-11-15。本报告依据双节点的 44 个原始文件整理；数据解析、图表和辅助脚本在发布阶段补充。原始日志保持字节不变，可通过 [SHA-256 清单](../data/manifest.json) 校验。

## 结论

在两台 GPU 云 VM 上，通过 `rdma_rxe` 建立了软件 RoCEv2 通信链路。`rping` 和 RC pingpong 完成，独立抓包记录到 UDP 4791 与 RC 数据/ACK 报文；NCCL 的两端日志确认使用 `NET/IB`、设备 `rxe0`，AllReduce 所有尺寸、两种缓冲模式的校验错误均为零。

在本次会话中，TCP 的吞吐高于 Soft-RoCE：单 QP RDMA Write 扫描的最高逐尺寸平均带宽为 **3.03 Gb/s**；iperf3 单流接收 **9.76 Gb/s**、四流接收 **10.7 Gb/s**。NCCL 在 256 MiB、out-of-place 模式下，RDMA 与 Socket 的 busbw 分别为 **0.20 和 0.57 GB/s**。软件 RDMA 的功能验证成立，性能结论限于本平台、本次配置和会话。

## 环境和拓扑

两台 VM 通过私网 `ens3` 互联，`rxe0` 建在该接口之上。节点 A（`brilliant-franklin`，`10.0.0.163`）承担服务端及 MPI rank 0；节点 B（`clever-tesla`，`10.0.0.103`）承担客户端及 rank 1。

| 项目 | 配置及证据 |
|---|---|
| 云平台与规格 | 实验笔记记录 Hyperstack NORWAY-1；每台 4 vCPU / 21 GB RAM，未附云平台资源导出 |
| GPU | 每台 RTX A4000 ×1；驱动 570.195.03，见两端 `nvidia_*.txt` |
| 系统 | Ubuntu 24.04 软件包；内核 `6.14.0-37-generic` |
| RDMA / perftest | rdma-core `50.0-2ubuntu0.2`；perftest `24.01.0+0.38-1build2` |
| rxe | `PORT_ACTIVE`，Ethernet，active MTU 4096，IPv4 RoCEv2 GID index 1 |
| CUDA | Toolkit 12.8，`nvcc V12.8.93` |
| NCCL | 成功运行日志为 `2.32.6+cuda12.9` |
| MPI / nccl-tests | OpenMPI 4.1.6；nccl-tests 2.21.1，`afd59ab` |

两端早期 `versions_*.txt` 记录了最初安装的 CUDA 13.5 构建。`apt_nccl_swap_*` 随后记录了替换为 CUDA 12.9 构建，最终以成功运行时日志为准。NIC 的以太网 MTU 未归档，不能把 rxe 的 active MTU 当成以太网 MTU。NCCL 日志明确显示 GPUDirect RDMA 已关闭，GPU 数据经主机内存中转。

## 实验过程与证据

1. 两端加载 `rdma_rxe`、创建 `rxe0`，检查端口状态与 GID。防火墙需要允许两节点间的 RDMA、测试工具及 MPI 通信；ICMP/SSH 通不等于 RDMA 通。
2. `rping` 客户端与服务端均留下 10 次数据交换，服务端记录断开事件。
3. RC pingpong 记录 1000 次往返：客户端总计 8,192,000 B，327.03 µs/iteration，200.40 Mbit/s。该工具按“消息大小 × 次数 × 2”计算总字节，因此单条消息为 **4096 B**。原报告将总量误写成单次 8 MB，并误用了 GID 参数；正确参数是 `-g`。
4. 独立 PCAP 包含 200 个双向 UDP 4791 报文，160 个 RC SEND 分段及 40 个 ACK。抓包的 QP 编号与已保存 pingpong 时序日志不同，表明它们属于不同会话；这里将抓包用于协议验证，不用于逐包解释该时序结果。
5. perftest 完成单 QP Write 带宽和时延扫描；另跑四 QP 扫描、CPU 采样与 iperf3 基线。完整扫描以客户端输出为准，服务端日志并非都有完整表。
6. nccl-tests 广泛构建在 GIN 子目标出现链接错误；AllReduce 主目标已生成，随后单机冒烟和双机运行成功。双机 RDMA 和 Socket 日志均含传输选择、26 个尺寸的结果、零校验错误及结束标志。

## 结果

| 测试 | 观测值 |
|---|---|
| RDMA Write 单 QP | 2 B–8 MiB，5000 iterations/size；128 KiB 最高平均 3.03 Gb/s；64 KiB 为 2.98 Gb/s |
| RDMA Write 时延 | 1000 iterations/size；2 B 平均 91.87 µs；4 KiB 为 122.05 µs；64 KiB 为 333.30 µs；8 MiB 为 23.815 ms |
| RDMA Write 四 QP | 19 个较小尺寸完成；1 MiB 行随后出现 completion status 5，标为无效；更大尺寸没有完成 |
| iperf3 单流 | 30 s，发送 9.77、接收 9.76 Gb/s |
| iperf3 四流 | 30 s，合计发送/接收均为 10.7 Gb/s（日志显示精度） |
| NCCL 256 MiB，out-of-place | RDMA 0.20 GB/s、1,358,372 µs；Socket 0.57 GB/s、471,638 µs |
| NCCL 256 MiB，in-place | RDMA 0.19 GB/s；Socket 0.58 GB/s |
| NCCL 工具报告的扫描平均 busbw | RDMA 0.0765298 GB/s；Socket 0.204685 GB/s |

NCCL 的扫描平均值混合了不同尺寸与两种缓冲模式，不能代替大消息平台带宽或独立重复实验均值。所有绘图使用日志中实际打印的精度，不恢复或编造额外有效数字。[完整 CSV 与图表](../results/README.md)

## 分析与局限

**CPU 开销可见，但根因尚未完全隔离。** 双端 aggregate `top` 数据显示协议处理期间有 CPU 活动；发送端还出现 nice time 与 CPU steal。由于没有时间戳、进程归属和同步采样窗口，也没有保存对应 duration-mode 的带宽输出，不能把各项百分比精确分配给 rxe 或用户态轮询，不能据此宣布“整机 CPU 上限为 3 Gb/s”。

**四 QP 失败需要保留。** `status 5` 对应 `IBV_WC_WR_FLUSH_ERR`，不是重试耗尽的枚举值。日志不能确定最初触发 QP 错误的原因；1 MiB 行及后续尺寸不用于成功性能结论。[上游状态定义](https://github.com/linux-rdma/rdma-core/blob/v50.0/libibverbs/verbs.h#L461-L474)

**队列深度是相关因素，但没有单变量实验。** Write 带宽扫描的 TX depth 为 128，Write 时延为 1；pingpong 的操作语义、同步方式、消息大小均不同。不能把约 200 Mbit/s 与 3.03 Gb/s 的全部差距都归因于队列深度。

**性能对比需保持口径。** iperf3 与 RDMA Write 是不同 API 和工作负载，作为同一机器对的吞吐背景对照；NCCL 对比才对应相同 collective、尺寸和缓冲模式。TSO/GRO、虚拟化调度、CPU 亲和性等因素没有被控制或记录，因此不能精确拆分性能差距的来源。

本项目仅有一次实验会话、每个配置一次扫描。NCCL 每尺寸/模式有 20 次计时迭代，但没有独立重复试验、置信区间或硬件 RDMA 对照。未测量 PFC/ECN/DCQCN、交换机行为、硬件 RoCE 时延/带宽、GPUDirect RDMA 性能及两节点以上的扩展性。

## 复现与后续实验

原实验的五个主体步骤——安装环境、创建 rxe 与检查 GID、连通性与抓包、RDMA/TCP 基准、NCCL 双传输 AllReduce——均已执行并留下日志。四 QP 扩展测试的失败单独保留，不改变主流程已经完成这一事实。

[复现指南](reproduce.md) 将这些步骤整理为供读者使用的操作说明，并单列收尾操作。公开的运行脚本在发布阶段依据历史命令与笔记补充，已完成本地语法及命令构造检查；尚未使用这些新脚本重新执行整套云端实验。这说明的是后补脚本的验证范围，不代表原实验还缺一步，也不要求为本次发布追加 GPU 实验。

后续可以采用独立多轮实验、固定 CPU 亲和性、带时间戳的 per-core/per-process 采样、NIC offload 快照和统一会话编号，进一步定位性能来源。若加入硬件 RoCE，应作为单独对照，保持相同的消息大小、队列深度和 collective 口径。
