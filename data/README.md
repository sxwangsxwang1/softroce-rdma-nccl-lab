# Archived evidence

These 44 files were extracted byte-for-byte from the two experiment archives. Their contents have not been edited or anonymized. Public IPv4 addresses and obvious credential patterns were not found during publication review. The logs and capture retain the experiment's private addresses, temporary hostnames, MAC addresses, QP identifiers, and local paths so the evidence remains internally inspectable.

| Directory | Original hostname | Private address | Role | Files |
|---|---|---|---|---:|
| `raw/node-a/` | `brilliant-franklin` | `10.0.0.163` | Server; MPI launch node / rank 0 | 23 |
| `raw/node-b/` | `clever-tesla` | `10.0.0.103` | Client / rank 1 | 21 |

[manifest.json](manifest.json) records each file's size, SHA-256 digest, source archive, and member path. The original compressed archives are retained locally and excluded from Git to avoid publishing duplicates:

| Original archive | SHA-256 |
|---|---|
| `roce-lab-logs_brilliant-franklin.tar.gz` | `058868375ff4e3521f1db5754990d6bf92221412cea7d0279978b4f236bd2127` |
| `roce-lab-logs_clever-tesla.tar.gz` | `8d6aa1295b260f729927591cf469112e317a3802601d9339f97383309e6b541a` |

NCCL output from both ranks was collected in the launch-node logs. It is not duplicated under node B. Some server-side perftest logs contain only setup and a final row; the full message-size scan comes from the client. Early `versions_*.txt` files precede the NCCL package replacement. Build logs include real GIN target failures even though the AllReduce binary was built and later executed successfully.

Run `python3 analysis/summarize.py --check` from the repository root to verify the raw hashes and all derived tables. The parser is deliberately specific to this archived experiment; new runs under ignored `runs/` do not replace or append to the published baseline automatically.
