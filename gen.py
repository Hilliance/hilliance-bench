#!/usr/bin/env python3
"""Generate a synthetic product population as JSON Lines.

Deterministic: the same --seed and --count always produce the same file, so a
benchmark run on your machine is comparable with one on ours.

    python3 gen.py --count 200000 --out products.jsonl

The population is deliberately awkward in the ways real catalogues are: the
same quantity arrives in two units, the same field under two spellings, and
plenty of rows simply lack a property. That is not decoration — it is what the
engine is being asked to cope with, and a population without it would make the
numbers look better than they are.
"""
import argparse
import json
import random

TYPES = {
    # type: (capacity ml low, high, weight g low, high)
    "mug": (280, 480, 220, 520),
    "travel mug": (350, 600, 260, 540),
    "teacup": (150, 260, 120, 300),
    "espresso cup": (60, 120, 80, 180),
    "tumbler": (250, 450, 200, 420),
    "wine glass": (300, 620, 140, 320),
    "beer glass": (330, 700, 180, 440),
    "bowl": (400, 900, 260, 700),
    "plate": (None, None, 300, 900),
    "kettle": (1200, 2400, 700, 1800),
}
BRANDS = ["Hägerlund", "Altvik", "Lera", "Brunn & Söner", "Söderbo", "Vitmark", "Kärnhem", "Norrvik"]
SERIES = ["Flis", "Knopp", "Lugn", "Bruk", "Sten", "Hav", "Höst", "Vinter", "Dagg", "Skog"]
COLOURS = ["mustard", "sage green", "black", "sky blue", "terracotta", "off-white", "navy",
           "rust", "charcoal", "sand", "forest green", "blush", "grey", "cream", "ochre"]
MATERIALS = ["stoneware", "porcelain", "glass", "bone china", "stainless steel", "plastic",
             "borosilicate glass", "earthenware"]
PATTERN = ["plain", "striped", "speckled", "floral", "hand-painted rim", "reactive glaze"]
FINISH = ["glossy", "matte", "satin", "brushed", "raw"]
ORIGIN = ["Germany", "Poland", "China", "Portugal", "Sweden", "Turkey", "Italy", "Vietnam"]


def rows(count, seed=7, titles=False):
    rnd = random.Random(seed)
    for i in range(count):
        t = rnd.choice(list(TYPES))
        cap_lo, cap_hi, w_lo, w_hi = TYPES[t]
        colour = rnd.choice(COLOURS)
        material = rnd.choice(MATERIALS)
        series = rnd.choice(SERIES)
        o = {
            "sku": "P%07d" % i,
            "type": t,
            "brand": rnd.choice(BRANDS),
            "series": series,
            "material": material,
            "origin": rnd.choice(ORIGIN),
            "price": round(rnd.lognormvariate(3.0, 0.7), 2),
            "in_stock": rnd.random() < 0.7,
            "dishwasher_safe": rnd.random() < 0.85,
        }
        # the same property, spelled two ways across the population
        o["colour" if rnd.random() < 0.5 else "color"] = colour
        # the same quantity, in two units
        if cap_lo:
            ml = rnd.randint(cap_lo, cap_hi)
            if rnd.random() < 0.65:
                o["capacity_ml"] = ml
            else:
                o["capacity_l"] = round(ml / 1000, 2)
        if rnd.random() < 0.6:
            cm = rnd.randint(w_lo, w_hi) / 10
            if rnd.random() < 0.6:
                o["diameter_cm"] = round(cm, 1)
            else:
                o["diameter_mm"] = round(cm * 10)
        # and plenty of absence
        if rnd.random() < 0.55:
            o["weight_g"] = rnd.randint(max(1, w_lo // 2), w_hi)
        if rnd.random() < 0.75:
            o["pattern"] = rnd.choice(PATTERN)
        if rnd.random() < 0.6:
            o["finish"] = rnd.choice(FINISH)
        if rnd.random() < 0.3:
            o["set_size"] = rnd.choice([1, 2, 4, 6, 12])
        if titles:
            # a near-unique free-text property: the hard case for search
            o["title"] = "%s %s %s in %s, %s (%d)" % (
                o["brand"], series, t, material, colour, i)
        yield o


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=200000, help="objects to generate")
    ap.add_argument("--seed", type=int, default=7, help="same seed, same file")
    ap.add_argument("--titles", action="store_true",
                    help="add a near-unique free-text title to every row")
    ap.add_argument("--out", default="products.jsonl")
    a = ap.parse_args()

    n = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for o in rows(a.count, a.seed, a.titles):
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
            n += 1
    print("%s: %d objects, seed %d%s" % (a.out, n, a.seed, ", with titles" if a.titles else ""))


if __name__ == "__main__":
    main()
