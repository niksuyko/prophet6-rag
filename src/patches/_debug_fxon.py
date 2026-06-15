"""Find the true master-FX-on offset (offset 54 looks wrong — 2/3 of effect patches
show fx.on=False). A real FX-enable byte should be HIGH for audible-fx patches, LOW for
no-fx patches."""
import glob
import json

pats = [json.load(open(f, encoding="utf-8")) for f in glob.glob("data/patches/p6-*.json")]


def hasfx(p):
    q = p["params"]
    return (q["fxa.type"] != "off" and q["fxa.mix"] > 0) or \
           (q["fxb.type"] != "off" and q["fxb.mix"] > 0)


withfx = [p for p in pats if hasfx(p)]
nofx = [p for p in pats if not hasfx(p)]
print(f"{len(withfx)} patches with audible fx, {len(nofx)} without")
print("offset [type ] %=nonzero among WITH-fx | among NO-fx  (master enable: HIGH/LOW)")
for off in range(44, 61):
    vals = set(p["raw"][off] for p in pats)
    binary = "bin" if vals <= {0, 1} else "multi"
    a = sum(1 for p in withfx if p["raw"][off]) / max(1, len(withfx))
    b = sum(1 for p in nofx if p["raw"][off]) / max(1, len(nofx))
    print(f"  {off:>3} [{binary:>5}] with-fx={a*100:5.1f}%   no-fx={b*100:5.1f}%")
