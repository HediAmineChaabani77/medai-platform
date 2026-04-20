"""Smoke-test BAAI/bge-reranker-v2-m3 on a controlled medical query.

We feed the reranker a chest-pain query and a mix of relevant (cardiac,
coronary, thrombolytic) and irrelevant (homeopathy, vitamin D, minoxidil)
BDPM-style passages. A working reranker must score the cardiac ones higher.
CPU-only to avoid fighting with the main LLM on the GTX 1650.
"""
from __future__ import annotations

import sys
import time

QUERY = "douleur thoracique constrictive avec irradiation bras gauche et sueurs, suspicion de syndrome coronarien"

PASSAGES = [
    ("cardiac-1",  "ASPIRINE 100 mg — antiagrégant plaquettaire. Indication : prévention secondaire des événements coronariens, syndrome coronarien aigu."),
    ("cardiac-2",  "ACTILYSE — alteplase, activateur du plasminogène tissulaire. Traitement thrombolytique de l'infarctus du myocarde à la phase aiguë."),
    ("cardiac-3",  "ATORVASTATINE — inhibiteur de l'HMG-CoA réductase. Prévention cardiovasculaire chez le patient à haut risque."),
    ("homeo-1",    "BOLDO BOIRON — degré de dilution 2CH à 30CH ou 4DH à 60DH. Préparation homéopathique à base de BOLDO."),
    ("minox-1",    "ALOSTIL 5 % — minoxidil. Solution pour application cutanée, alopécie androgénétique masculine."),
    ("vitd-1",     "A 313 200 000 UI POUR CENT — pommade vitaminée A. Indication dermatologique."),
    ("restless-1", "ADARTREL — ropinirole. Syndrome des jambes sans repos idiopathique, formes modérées à sévères."),
]


def main():
    from sentence_transformers import CrossEncoder
    t0 = time.perf_counter()
    model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512, device="cpu")
    print(f"[load]  {time.perf_counter() - t0:.1f}s")

    t1 = time.perf_counter()
    pairs = [(QUERY, p[1]) for p in PASSAGES]
    scores = model.predict(pairs)
    print(f"[infer] {time.perf_counter() - t1:.2f}s for {len(PASSAGES)} pairs")

    ranked = sorted(zip(PASSAGES, scores), key=lambda x: x[1], reverse=True)
    print("\nRank  Score      Id          Text")
    print("-" * 100)
    for i, ((pid, text), score) in enumerate(ranked, 1):
        print(f"{i:>3}   {score:+.4f}   {pid:<10}  {text[:70]}...")

    # Sanity: top result must be one of the cardiac passages.
    top_id = ranked[0][0][0]
    assert top_id.startswith("cardiac"), f"top result is {top_id!r}, expected cardiac-*"
    print("\nOK: cardiac passage ranked first.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"FAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}"); sys.exit(1)
