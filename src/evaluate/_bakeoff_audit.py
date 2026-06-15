"""Audit bakeoff_v2 judge rationales for the citation-blindness artifact: verdicts
where the judge calls (true) factory-preset/parameter references 'fabricated'."""
import json
import re
from pathlib import Path

RES = Path(__file__).resolve().parents[2] / "eval" / "results"
d = json.loads(sorted(RES.glob("*bakeoff_v2.json"))[-1].read_text(encoding="utf-8"))

fab_against_rag = []
for q in d["per_query"]:
    j = q["judge"]
    reason = j.get("reason", "") if isinstance(j, dict) else str(j)
    winner = q["outcome"]
    if re.search(r"fabricat|invent|made.up|hallucinat", reason, re.I) and winner == "base":
        fab_against_rag.append((q["id"], reason[:130]))

print(f"base wins where the judge alleged fabrication: {len(fab_against_rag)} "
      f"of {d['totals']['base']} base wins")
for qid, r in fab_against_rag:
    print(f"  {qid}: {r}")

# how many of those allege fabricated *preset* references (verifiably true for RAG)
preset = [x for x in fab_against_rag if re.search(r"preset|factory|patch", x[1], re.I)]
print(f"\n...of which allege fabricated preset/factory references: {len(preset)}")
