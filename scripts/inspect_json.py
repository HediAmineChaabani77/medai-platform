#!/usr/bin/env python3
"""Pretty-print a UC response for quality review."""
import json
import sys

path = sys.argv[1]
uc = sys.argv[2] if len(sys.argv) > 2 else "uc1"
d = json.load(open(path))

if uc == "uc1":
    print("rule:", d.get("rule"), "| provider:", d.get("provider_used"), "| audit:", d.get("audit_id"))
    for x in d.get("diagnoses", []):
        print(f"  * {x['condition']:<45} p={x['probability']:.2f}  icd10={x.get('icd10')}")
        print(f"    reasoning: {x['reasoning'][:220]}")
    print("red_flags:", d.get("red_flags"))
    print("--- citations ---")
    for c in d.get("citations", []):
        print(f"  [{c['id']}] {c['source']}  - {c['section'][:80]}")
    print("--- raw ---")
    print((d.get("raw_answer") or "")[:600])

elif uc == "uc2":
    print("rule:", d.get("rule"), "| provider:", d.get("provider_used"), "| audit:", d.get("audit_id"))
    print("signature:", (d.get("signature") or "")[:16], "...")
    print("--- markdown ---")
    print(d.get("markdown", ""))
    print("--- sections ---")
    for s in d.get("sections", []):
        print(f"  [{s['title']}] {s['content'][:150]}")

elif uc == "uc3":
    det = d.get("detail", d)
    print("blocked:", det.get("blocked"), "| max_severity:", det.get("max_severity"), "| rule:", det.get("rule"))
    print("--- alerts ---")
    for a in det.get("alerts", []):
        print(f"  [{a['severity'].upper()}] {a['type']}: {a.get('drug_a')} + {a.get('drug_b')} -- {a['mechanism']}")
    print("--- explanation ---")
    print((det.get("explanation") or "")[:800])
