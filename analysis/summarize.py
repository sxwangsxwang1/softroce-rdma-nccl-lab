#!/usr/bin/env python3
"""Derive tables from the archived run without changing raw evidence. Python 3.10+."""

import argparse
import csv
import hashlib
import io
import json
import re
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"


def parse_perftest(text, latency=False):
    rows = []
    fields = 9 if latency else 5
    for line_no, line in enumerate(text.splitlines(), 1):
        match = re.match(r"^\s*(\d+)\s+(\d+)\s+(.+)$", line)
        if not match:
            continue
        tail = re.match(r"\s+".join([f"({NUMBER})"] * (fields - 2)), match[3])
        if not tail:
            raise ValueError(f"Incomplete perftest row at line {line_no}")
        values = [int(match[1]), int(match[2]), *map(float, tail.groups())]
        valid = not match[3][tail.end():].strip()
        rows.append((values, valid, line_no))
    if not rows:
        raise ValueError("No perftest rows found")
    # An error after a printed row makes that last measurement incomplete.
    if re.search(r"Completion with error|Failed to complete run_iter", text):
        values, _, line_no = rows[-1]
        rows[-1] = (values, False, line_no)
    return rows


def parse_nccl(text):
    """Recover rows whose prefix and numeric tail are split by MPI debug output."""
    prefix = re.compile(r"^\s*(\d+)\s+(\d+)\s+float\s+sum\s+(-?\d+)")
    numeric = re.compile(r"^\s*" + r"\s+".join([f"({NUMBER})"] * 8) + r"\s*$")
    pending = None
    rows = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = prefix.match(line)
        if match:
            if pending:
                raise ValueError(f"Unfinished NCCL row before line {line_no}")
            pending = (int(match[1]), int(match[2]), line_no)
            line = line[match.end():]
        tail = numeric.fullmatch(line)
        if tail and pending:
            size, count, source_line = pending
            values = list(map(float, tail.groups()))
            if not values[3].is_integer() or not values[7].is_integer():
                raise ValueError("Noninteger NCCL validation counts")
            values[3], values[7] = int(values[3]), int(values[7])
            rows.append([size, count, *values, source_line])
            pending = None
    if pending:
        raise ValueError("Unfinished final NCCL row")
    average = re.search(r"# Avg bus bandwidth\s*:\s*(" + NUMBER + ")", text)
    if not average or "# Out of bounds values : 0 OK" not in text:
        raise ValueError("NCCL completion/validation summary is absent")
    if "# Collective test concluded: all_reduce_perf" not in text:
        raise ValueError("NCCL run did not conclude")
    return rows, float(average[1])


def inspect_pcap(payload):
    if payload[:4] != b"\xd4\xc3\xb2\xa1":
        raise ValueError("Expected little-endian microsecond PCAP")
    if struct.unpack_from("<I", payload, 20)[0] != 1:
        raise ValueError("Expected Ethernet capture")
    offset, packets = 24, 0
    flows, opcodes, lengths = Counter(), Counter(), Counter()
    timestamps = []
    while offset < len(payload):
        sec, usec, captured, original = struct.unpack_from("<IIII", payload, offset)
        offset += 16
        packet = payload[offset:offset + captured]
        offset += captured
        if len(packet) != captured or original != captured:
            raise ValueError("Truncated PCAP record")
        if packet[12:14] != b"\x08\x00":
            raise ValueError("Non-IPv4 frame")
        ip = packet[14:]
        ihl = (ip[0] & 15) * 4
        if ip[9] != 17 or struct.unpack_from("!H", ip, 6)[0] & 0x3FFF:
            raise ValueError("Expected unfragmented UDP")
        udp = ip[ihl:]
        sport, dport, length = struct.unpack_from("!HHH", udp)
        if dport != 4791 or len(udp) < length:
            raise ValueError("Expected complete RoCEv2 UDP payload")
        bth = udp[8:length]
        if len(bth) < 12:
            raise ValueError("Missing BTH")
        src = ".".join(map(str, ip[12:16]))
        dst = ".".join(map(str, ip[16:20]))
        flows[f"{src}:{sport} -> {dst}:{dport}"] += 1
        opcodes[f"0x{bth[0]:02x}"] += 1
        lengths[str(len(bth))] += 1
        timestamps.append(sec + usec / 1_000_000)
        packets += 1
    if offset != len(payload):
        raise ValueError("PCAP length mismatch")
    return {
        "packets": packets,
        "capture_span_ms": round((max(timestamps) - min(timestamps)) * 1000, 3),
        "flows": dict(sorted(flows.items())),
        "bth_opcode_counts": dict(sorted(opcodes.items())),
        "udp_payload_bytes": dict(sorted(lengths.items())),
    }


def csv_text(headers, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return stream.getvalue()


def derive(root=ROOT):
    manifest = json.loads((root / "data/manifest.json").read_text())
    for entry in manifest["files"]:
        raw = (root / entry["path"]).read_bytes()
        if len(raw) != entry["bytes"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"Raw file changed: {entry['path']}")
    read = lambda node, name: (root / "data/raw" / node / name).read_text()
    artifacts = {}
    bw_headers = ["message_bytes", "iterations", "peak_gbps", "average_gbps", "message_rate_mpps", "valid", "source_line"]
    for filename, name in [("ib_write_bw_client.txt", "write_bw.csv"), ("ib_write_bw_q4_client.txt", "write_bw_q4.csv")]:
        rows = parse_perftest(read("node-b", filename))
        artifacts[name] = csv_text(bw_headers, [[*v, str(valid).lower(), line] for v, valid, line in rows])
    lat_headers = ["message_bytes", "iterations", "min_us", "max_us", "typical_us", "average_us", "stdev_us", "p99_us", "p999_us", "valid", "source_line"]
    rows = parse_perftest(read("node-b", "ib_write_lat_client.txt"), latency=True)
    artifacts["write_latency.csv"] = csv_text(lat_headers, [[*v, str(valid).lower(), line] for v, valid, line in rows])
    nccl_headers = ["transport", "message_bytes", "elements", "oop_time_us", "oop_algbw_GBps", "oop_busbw_GBps", "oop_wrong", "ip_time_us", "ip_algbw_GBps", "ip_busbw_GBps", "ip_wrong", "source_line"]
    nccl_rows, averages = [], {}
    for transport in ("rdma", "socket"):
        rows, average = parse_nccl(read("node-a", f"nccl_allreduce_{transport}.txt"))
        if [r[0] for r in rows] != [2**n for n in range(3, 29)]:
            raise ValueError(f"Missing/duplicate NCCL size: {transport}")
        if any(r[5] or r[9] for r in rows):
            raise ValueError(f"NCCL validation errors: {transport}")
        nccl_rows.extend([[transport, *row] for row in rows])
        averages[transport] = average
    artifacts["nccl_allreduce.csv"] = csv_text(nccl_headers, nccl_rows)
    cpu_rows = []
    for node, filename in [("node-a", "cpu_during_ib_write_bw.txt"), ("node-b", "cpu_during_ib_write_bw_client.txt")]:
        for idx, line in enumerate(read(node, filename).splitlines(), 1):
            values = dict((name, float(value)) for value, name in re.findall(r"([\d.]+)\s+(us|sy|ni|id|wa|hi|si|st)", line))
            if len(values) != 8:
                raise ValueError(f"Malformed CPU sample: {node}:{idx}")
            cpu_rows.append([node, idx, *[values[key] for key in ("us", "sy", "ni", "id", "wa", "hi", "si", "st")]])
    artifacts["cpu_samples.csv"] = csv_text(["node", "sample_index", "user_pct", "system_pct", "nice_pct", "idle_pct", "iowait_pct", "irq_pct", "softirq_pct", "steal_pct"], cpu_rows)
    tcp_rows = []
    for streams in (1, 4):
        name = f"iperf3_{streams}stream.txt"
        for line_no, line in enumerate(read("node-b", name).splitlines(), 1):
            if streams == 4 and not line.startswith("[SUM]"):
                continue
            match = re.search(r"([\d.]+)\s+Gbits/sec(?:\s+\d+)?\s+(sender|receiver)\s*$", line)
            if match:
                tcp_rows.append([streams, match[2], float(match[1]), line_no])
    if len(tcp_rows) != 4:
        raise ValueError("Missing iperf3 sender/receiver summaries")
    artifacts["tcp_baseline.csv"] = csv_text(["streams", "endpoint", "gbps", "source_line"], tcp_rows)
    capture = inspect_pcap((root / "data/raw/node-a/roce_v2.pcap").read_bytes())
    artifacts["capture_summary.json"] = json.dumps(capture, indent=2) + "\n"
    artifacts["nccl_summary.json"] = json.dumps({"reported_scan_average_busbw_GBps": averages, "socket_over_rdma_scan_average": averages["socket"] / averages["rdma"], "note": "Tool-reported average across message sizes and both buffer modes; not a repeated-run statistic."}, indent=2) + "\n"
    return artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify raw hashes and compare committed derived tables")
    args = parser.parse_args()
    outputs = derive()
    for name, content in outputs.items():
        path = ROOT / "results" / name
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Derived output differs: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    print(f"Verified 44 raw-file hashes and {'checked' if args.check else 'wrote'} {len(outputs)} derived files.")


if __name__ == "__main__":
    main()
