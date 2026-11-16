"""Validate command construction and error propagation without running network tests."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from analysis.summarize import ROOT


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        stub = '#!/usr/bin/env bash\nprintf "%s\\n" "$@"\nexit "${STUB_EXIT:-0}"\n'
        for name in ("ib_write_bw", "ib_write_lat", "ibv_rc_pingpong", "rping", "iperf3", "mpirun"):
            target = self.bin / name
            target.write_text(stub)
            target.chmod(0o755)
        executable = self.base / "nccl/build/all_reduce_perf"
        executable.parent.mkdir(parents=True)
        executable.write_text(stub)
        executable.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "RUN_DIR": str(self.base / "runs"), "NIC": "ens3", "GIDX": "7", "RXE": "rxe0", "NCCL_TESTS_DIR": str(self.base / "nccl"), "LOCAL_IP": "10.0.0.163"}

    def run_script(self, name, *args, exitcode=0):
        result = subprocess.run(["bash", str(ROOT / "scripts" / name), *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, exitcode, result.stderr)
        return result.stdout.splitlines()

    def test_client_server_address_and_tool_gid_flags(self):
        args = self.run_script("run_perftest.sh", "client", "write-bw", "10.0.0.163")
        self.assertEqual(args[-1], "10.0.0.163")
        self.assertEqual(args[args.index("-x") + 1], "7")
        server = self.run_script("run_perftest.sh", "server", "pingpong")
        self.assertNotIn("10.0.0.163", server)
        self.assertEqual(server[server.index("-g") + 1], "7")
        self.assertEqual(server[server.index("-s") + 1], "4096")

    def test_failure_is_preserved_and_recorded(self):
        self.env["STUB_EXIT"] = "5"
        self.run_script("run_perftest.sh", "client", "write-bw-q4", "10.0.0.163", exitcode=5)
        self.assertEqual((self.base / "runs/write-bw-q4_client.txt.exitcode").read_text(), "5\n")

    def test_tcp_client_and_rping_do_not_get_extra_address(self):
        tcp = self.run_script("run_perftest.sh", "client", "tcp4", "10.0.0.163")
        self.assertEqual(tcp.count("10.0.0.163"), 1)
        self.assertEqual(tcp[tcp.index("-P") + 1], "4")
        rping = self.run_script("run_perftest.sh", "client", "rping", "10.0.0.163")
        self.assertEqual(rping.count("10.0.0.163"), 1)

    def test_nccl_transport_and_failed_exit(self):
        rdma = self.run_script("run_nccl.sh", "rdma", "10.0.0.163", "10.0.0.103")
        self.assertIn("NCCL_IB_DISABLE=0", rdma)
        self.assertIn("NCCL_IB_GID_INDEX=7", rdma)
        self.assertIn("NCCL_NET_GDR_LEVEL=0", rdma)
        socket = self.run_script("run_nccl.sh", "socket", "10.0.0.163", "10.0.0.103")
        self.assertIn("NCCL_IB_DISABLE=1", socket)
        self.assertFalse(any(arg.startswith("NCCL_IB_HCA=") for arg in socket))
        self.env["STUB_EXIT"] = "7"
        self.run_script("run_nccl.sh", "rdma", "10.0.0.163", "10.0.0.103", exitcode=7)
        self.assertEqual((self.base / "runs/nccl_allreduce_rdma.txt.exitcode").read_text(), "7\n")


if __name__ == "__main__":
    unittest.main()
