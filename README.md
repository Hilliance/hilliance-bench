# Hilliance benchmarks

Reproduce the figures [hilliance.com](https://hilliance.com) quotes, on your own
machine, against the published image. Two files, no dependencies beyond Python 3
and Docker, and nothing here needs the engine's source.

```bash
docker run -d -p 8080:8080 -v hilliance-data:/data hilliance/hilliance
python3 gen.py --count 200000 --out products.jsonl
python3 bench.py --objects products.jsonl --json results/mine.json
```

That is the whole thing. `gen.py` writes a synthetic catalogue, `bench.py`
learns it and times a set of queries through the ordinary HTTP API.

> **A named volume, not a host directory.** The image runs as uid 10001, so a
> bind mount like `-v "$PWD/data:/data"` is not writable by the server on Linux
> and the first upload fails with `Permission denied`. macOS hides this; CI does
> not. Use a named volume, or `chown 10001:999` the directory first.

## Why this repository exists

Every performance claim on the site came from a machine you cannot see, on data
you cannot download. That is the usual state of affairs and it is not good
enough: a benchmark you cannot run is a press release. This repository is the
smallest thing that fixes it — the data is generated from a seed, the queries
are written down, and the timings come from the same public image anyone can
pull.

If your numbers disagree with ours, the disagreement is the useful part. Open an
issue with your `results/*.json` and what the machine was.

## What is measured

`bench.py` reports two numbers per query, because they answer different
questions:

| | |
|---|---|
| **engine** | what the server says it spent searching (`took_us`) — the figure the documentation quotes |
| **client** | wall clock from the Python process: JSON, sockets and the client itself included — always larger, and closer to what your application feels |

Both are medians over `--repeat` runs (31 by default) after `--warmup`
discarded ones. `blocks` is how much of the population the search had to read:
`1 / 196` means one block of 196 was touched, and that ratio is the whole trick
behind the small numbers.

## A run, in full

200,000 objects on an Apple M3 Pro (12 cores, 16 GB), Docker Desktop 27.3.1,
`hilliance/hilliance:1.0.0`, arm64 with the `dotprod` kernel. Raw output in
[`results/macbook-m3pro-200k.json`](results/macbook-m3pro-200k.json).

| Query | Engine | Client | Blocks |
|---|---|---|---|
| exact type | 23 µs | 1.3 ms | 1 / 196 |
| type + colour + capacity | 22 µs | 1.2 ms | 2 / 196 |
| values never seen | 23 µs | 950 µs | 1 / 196 |
| rich, eight properties | 369 µs | 1.9 ms | 63 / 196 |
| numbers only | 384 µs | 1.3 ms | 103 / 196 |
| weak evidence | 17 µs | 1.1 ms | 1 / 196 |
| cross-unit, cross-spelling | 23 µs | 927 µs | 2 / 196 |
| filtered: in stock, 10–25 | 32 µs | 885 µs | 3 / 196 |

Learning those 200,000 objects took **4.0 s**, streamed as 55.7 MB of JSON
Lines.

Three things worth reading off that table rather than the headline:

- **The spread is twenty-fold.** A selective query reads one block of 196; a
  rich one reads 63 and an all-numeric one 103. Quoting only the first number
  would be flattering and useless.
- **The client column is the one your users feel.** At this size the engine is a
  rounding error inside an HTTP round trip from Python. That is a compliment to
  the engine and a warning about benchmark theatre.
- **The awkward query is not slow.** `cross-unit, cross-spelling` asks with
  `color` where half the population says `colour`, and in litres where it is
  stored in millilitres. It costs the same as asking the easy way, because the
  reconciliation happened once, at learn time.

## The population

`gen.py` is deliberately messy, in the ways catalogues are:

- half the rows carry `colour`, half `color`;
- capacity arrives as `capacity_ml` or `capacity_l`, diameter as
  `diameter_cm` or `diameter_mm`;
- most properties are missing from some rows, because real ones are.

A tidy population would make the engine look better and tell you less. Use
`--titles` to add a near-unique free-text field, which is the case that costs
milliseconds rather than microseconds:

```bash
python3 gen.py --count 1000000 --titles --out titles.jsonl
```

## Checking that the numbers mean anything

Speed is only interesting if the results are right. Every query takes
`"exhaustive": true`, which turns pruning off and scans everything:

```bash
curl -X POST localhost:8080/spaces/bench/search -H 'content-type: application/json' \
  -d '{"object": {"type": "mug", "colour": "mustard"}, "limit": 10, "exhaustive": true}'
```

The matches and their scores should be identical to the pruned run, in the same
order. If they ever differ, that is a bug worth an issue — pruning is supposed
to change the time and nothing else.

## Options

```
gen.py    --count N        objects to generate (default 200000)
          --seed N         same seed, same file (default 7)
          --titles         add a near-unique free-text title
          --out FILE

bench.py  --url URL        default http://localhost:8080
          --key SECRET     if the server wants one (or $HILLIANCE_KEY)
          --objects FILE   JSON Lines to learn
          --space NAME     default "bench"
          --limit N        matches per query (default 10)
          --repeat N       timed runs (default 31)
          --warmup N       discarded runs (default 5)
          --skip-learn     the Space already exists
          --json FILE      write the raw results
```

## Honest notes

- **Synthetic data is synthetic.** The population has structure a real catalogue
  has — categories, correlated properties, missing values — but your data will
  behave differently, and the only number that matters to you is the one from
  your own.
- **First call versus warm.** Artifacts are memory-mapped, so the first query
  after a load pays for page faults. That is what `--warmup` is for; drop it to
  zero if cold starts are what you care about.
- **One machine, one container.** These figures include Docker's filesystem and
  network layers. Running the binary directly is faster; running on a busy host
  is slower.
- **The engine's own suite measures more** — 2M objects, sharding, replicas,
  the sustained-load soak — and those numbers are in the
  [documentation](https://hilliance.com/docs.html#performance). This repository
  covers what can be reproduced from the published image alone.

## Licence

The harness in this repository is MIT (see [LICENSE](LICENSE)). Hilliance itself
is a separate work under the Business Source License 1.1: free to self-host,
including in production, with a commercial licence required only to offer it to
third parties as a hosted service. Questions: `info@hilliance.com`.
