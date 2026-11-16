#!/usr/bin/env python3
"""Render the committed CSV tables with Matplotlib; no hardware is required."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
BLUE, ORANGE, GRAY = "#2563eb", "#e87924", "#64748b"


def read(name):
    with (ROOT / "results" / name).open() as stream:
        return list(csv.DictReader(stream))


def size_axis(axis):
    axis.set_xscale("log", base=2)
    axis.set_xticks([2**i for i in (3, 10, 16, 20, 23, 28)])
    axis.set_xticklabels(["8 B", "1 KiB", "64 KiB", "1 MiB", "8 MiB", "256 MiB"])
    axis.set_xlabel("Message size")


def save(fig, name, note):
    fig.text(0.5, 0.015, note, ha="center", color=GRAY, fontsize=9)
    fig.tight_layout(rect=(0, 0.055, 1, 0.96))
    path = ROOT / "results/figures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "svg"):
        fig.savefig(path.with_suffix("." + suffix), dpi=180, metadata={"Date": None} if suffix == "svg" else {})
    plt.close(fig)


def main():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.17, "svg.hashsalt": "softroce-lab"})
    bw, q4, lat = read("write_bw.csv"), read("write_bw_q4.csv"), read("write_latency.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.5))
    for rows, label, color in ((bw, "1 QP", BLUE), (q4, "4 QPs (completed sizes)", ORANGE)):
        valid = [r for r in rows if r["valid"] == "true"]
        axes[0].plot([int(r["message_bytes"]) for r in valid], [float(r["average_gbps"]) for r in valid], "o-", ms=3, label=label, color=color)
    axes[0].axhline(9.76, ls="--", lw=1, color=GRAY, label="TCP 1 stream: 9.76 Gb/s received")
    axes[0].set(title="RDMA Write bandwidth", ylabel="Average bandwidth (Gb/s)", ylim=(0, 10.6))
    axes[0].annotate("3.03 Gb/s at 128 KiB", xy=(131072, 3.03), xytext=(3000, 5), arrowprops={"arrowstyle": "->", "color": BLUE}, color=BLUE)
    axes[0].legend(loc="upper left", fontsize=8)
    axes[1].plot([int(r["message_bytes"]) for r in lat], [float(r["average_us"]) for r in lat], "o-", ms=3, color=BLUE, label="Mean")
    axes[1].plot([int(r["message_bytes"]) for r in lat], [float(r["p99_us"]) for r in lat], "--", color=ORANGE, label="p99")
    axes[1].set_yscale("log")
    axes[1].set(title="RDMA Write latency", ylabel="perftest reported latency (µs)")
    axes[1].legend()
    for ax in axes:
        size_axis(ax)
        ax.set_xlim(2, 2**23)
        ax.set_xticks([2, 1024, 65536, 8388608], ["2 B", "1 KiB", "64 KiB", "8 MiB"])
    fig.suptitle("Soft-RoCE on two cloud VMs · 2026-11-15", fontsize=14)
    save(fig, "perftest", "One scan per configuration; 4-QP 1 MiB failure excluded. TCP is a separate throughput workload.")

    nccl = read("nccl_allreduce.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.5), sharey=True)
    for ax, prefix, title in zip(axes, ("oop", "ip"), ("Out-of-place", "In-place")):
        for transport, label, color in (("rdma", "RDMA / rxe", BLUE), ("socket", "TCP Socket", ORANGE)):
            rows = [r for r in nccl if r["transport"] == transport]
            ax.plot([int(r["message_bytes"]) for r in rows], [float(r[f"{prefix}_busbw_GBps"]) for r in rows], "o-", ms=3, label=label, color=color)
        ax.set(title=title, ylim=(0, 0.65))
        size_axis(ax)
        ax.set_xlim(8, 2**28)
        ax.legend(loc="upper left")
    axes[0].set_ylabel("NCCL bus bandwidth (GB/s)")
    fig.suptitle("NCCL AllReduce · 2 nodes × 1 RTX A4000 · all validation errors = 0", fontsize=14)
    save(fig, "nccl_allreduce", "One scan per transport; 20 timed iterations per size/mode. Plotted bandwidth is rounded in the source logs.")

    cpu = read("cpu_samples.csv")
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.5), sharey=True)
    for ax, node, title in zip(axes, ("node-a", "node-b"), ("Node A · receiver", "Node B · sender")):
        rows = [r for r in cpu if r["node"] == node][1:]
        samples = [int(r["sample_index"]) for r in rows]
        ax.stackplot(samples, *[[float(r[column]) for r in rows] for column in ("user_pct", "system_pct", "softirq_pct", "nice_pct", "steal_pct")], labels=["User", "System", "SoftIRQ", "Nice", "Steal"], colors=[BLUE, ORANGE, "#22a884", "#b15cc3", GRAY], alpha=0.85)
        ax.set(title=title, xlabel="Sample index within each local file", ylim=(0, 100))
        ax.legend(loc="upper left", fontsize=8, ncol=3)
    axes[0].set_ylabel("Aggregate CPU time (%)")
    fig.suptitle("CPU observations during the bandwidth session", fontsize=14)
    save(fig, "cpu_samples", "First top sample omitted. No timestamps or process attribution; nodes are not time-aligned. Idle/I/O-wait/IRQ omitted.")
    print("Rendered 3 figures in PNG and SVG formats.")


if __name__ == "__main__":
    main()
