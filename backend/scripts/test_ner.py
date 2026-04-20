"""Test Jean-Baptiste/camembert-ner for French PII detection in clinical notes.

Must flag PERSON names (Dupont, Marie Durand) and LOC (Paris). These augment
the regex-only PHI detector for the high-sensitivity routing rule.
"""
from __future__ import annotations

import sys
import time


TEXTS = [
    ("Mr Jean Dupont, 62 ans, domicilié à Paris, consulte pour HTA.", {"PER": 1, "LOC": 1}),
    ("Patient sans antécédent notable. Pas de fièvre.", {"PER": 0, "LOC": 0}),
    ("Mme Marie Durand née le 15/03/1962 à Lyon.", {"PER": 1, "LOC": 1}),
]


def main():
    from transformers import pipeline
    t0 = time.perf_counter()
    ner = pipeline(
        "token-classification",
        model="Jean-Baptiste/camembert-ner",
        aggregation_strategy="simple",
        device=-1,  # CPU
    )
    print(f"[load]  {time.perf_counter() - t0:.1f}s")

    for text, expected in TEXTS:
        t1 = time.perf_counter()
        ents = ner(text)
        dt = (time.perf_counter() - t1) * 1000
        per = sum(1 for e in ents if e["entity_group"] == "PER")
        loc = sum(1 for e in ents if e["entity_group"] == "LOC")
        print(f"\n{text!r}")
        print(f"  [{dt:.0f} ms] PER={per} LOC={loc} total_ents={len(ents)}")
        for e in ents:
            print(f"    {e['entity_group']:<5} score={e['score']:.2f} {e['word']!r}")
        assert per >= expected["PER"], f"PER count {per} < expected {expected['PER']}"
        assert loc >= expected["LOC"], f"LOC count {loc} < expected {expected['LOC']}"

    print("\nOK: NER flags PER and LOC correctly on all fixtures.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}"); sys.exit(1)
