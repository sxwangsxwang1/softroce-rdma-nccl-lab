"""Check the substantive publication failure cases against real archived evidence."""

import unittest

from analysis.summarize import ROOT, derive, inspect_pcap, parse_nccl, parse_perftest


class EvidenceTests(unittest.TestCase):
    def test_interleaved_nccl_rows_are_recovered(self):
        for transport in ("rdma", "socket"):
            with self.subTest(transport=transport):
                text = (ROOT / f"data/raw/node-a/nccl_allreduce_{transport}.txt").read_text()
                rows, _ = parse_nccl(text)
                self.assertEqual([r[0] for r in rows], [2**i for i in range(3, 29)])
                self.assertTrue(all(r[5] == r[9] == 0 for r in rows))
                self.assertGreater(rows[0][2], 0)
        rdma = (ROOT / "data/raw/node-a/nccl_allreduce_rdma.txt").read_text()
        self.assertEqual(next(r for r in parse_nccl(rdma)[0] if r[0] == 4096)[2], 351.28)

    def test_incomplete_nccl_run_is_rejected(self):
        text = (ROOT / "data/raw/node-a/nccl_allreduce_rdma.txt").read_text()
        with self.assertRaises(ValueError):
            parse_nccl(text[:text.index("# Out of bounds")])

    def test_q4_error_is_not_published_as_success(self):
        text = (ROOT / "data/raw/node-b/ib_write_bw_q4_client.txt").read_text()
        rows = parse_perftest(text)
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[-1][0][0], 1048576)
        self.assertFalse(rows[-1][1])
        self.assertTrue(all(valid for _, valid, _ in rows[:-1]))

    def test_capture_contains_bidirectional_data_and_ack(self):
        summary = inspect_pcap((ROOT / "data/raw/node-a/roce_v2.pcap").read_bytes())
        self.assertEqual(summary["packets"], 200)
        self.assertEqual(sorted(summary["flows"].values()), [100, 100])
        self.assertEqual(summary["bth_opcode_counts"], {"0x00": 40, "0x01": 80, "0x02": 40, "0x11": 40})

    def test_tables_match_raw_evidence(self):
        for name, contents in derive().items():
            with self.subTest(name=name):
                self.assertEqual((ROOT / "results" / name).read_text(), contents)


if __name__ == "__main__":
    unittest.main()
