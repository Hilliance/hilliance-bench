# Results

One JSON file per run, written by `bench.py --json`. Name them so the machine is
obvious: `macbook-m3pro-200k.json`, `ci-20261013.json`, `hetzner-ccx33-2m.json`.

Each file records the query timings, the blocks each search read, what the
server reported in `/health` (including which SIMD kernel it chose), and when it
ran. Numbers from different machines are not comparable in absolute terms; the
shape of the table — which queries are cheap, which are not — should be.

Send a pull request with yours, especially if it disagrees with ours.
