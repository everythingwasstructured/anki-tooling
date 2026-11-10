# -*- coding: utf-8 -*-
"""Assemble the audit bundle. The brief is a fixed template; only the facts change.

usage: python3 make_bundle.py --slug SLUG --cards cards.json --extract extract_out.txt
                              --media media --brief brief.json --out SLUG-audit.zip
                              [--captions captions.txt]

brief.json (facts about the job, never reasons for a card):
  {"lecture": "Introduction to Pharmacokinetics", "lecturer": "Dr A Grant",
   "sources": "32-slide PPTX, no speaker notes, captions of the in-class session",
   "scope": ["Slide 7 routes A-E are out (Kai)", "Text inside pictures is not carded, except slide 6"],
   "conventions": ["Image-occlusion notes cover figure labels and are not in this bundle"]}

The plan, cut list, rectification table, coverage map and every lint_ok / order reason stay
OUT of the bundle: they are the author's reasoning, and the audit has to be read cold.
"""
import os, sys, json, zipfile, argparse
ap = argparse.ArgumentParser()
for k in ("slug", "cards", "extract", "media", "brief", "out"): ap.add_argument("--" + k, required=True)
ap.add_argument("--captions")
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(here, "AUDIT-BRIEF.md"), encoding="utf-8").read()
b = json.load(open(a.brief, encoding="utf-8"))
doc = json.load(open(a.cards, encoding="utf-8"))
PRIVATE = ("covers", "lint_ok", "order", "stressed_quote")   # stressed_quote is already quoted in Extra
cards = [{k: v for k, v in c.items() if k not in PRIVATE} for c in doc["cards"]]
used = sorted({c["image"] for c in cards if c.get("image")})
missing = [m for m in used if not os.path.exists(os.path.join(a.media, m))]
if missing: sys.exit(f"media missing from {a.media}: {missing}")
bullets = lambda xs: "\n".join(f"- {x}" for x in xs) if xs else "- none"
brief = (tpl.replace("{{LECTURE}}", b["lecture"]).replace("{{LECTURER}}", b.get("lecturer", "not stated"))
            .replace("{{SOURCES}}", b.get("sources", "")).replace("{{SCOPE}}", bullets(b.get("scope")))
            .replace("{{CONVENTIONS}}", bullets(b.get("conventions")))
            .replace("{{COUNTS}}", f"{len(cards)} notes, {len(used)} figures on {sum(1 for c in cards if c.get('image'))} notes")
            .replace("{{CAPTIONS}}", "03-lecture-captions.txt   the machine-generated transcript" if a.captions
                     else "(no transcript exists for this lecture)"))
with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("00-AUDIT-BRIEF.md", brief)
    z.writestr("01-cards.json", json.dumps({"deck": doc.get("deck"), "cards": cards}, ensure_ascii=False, indent=1))
    z.write(a.extract, "02-slides-extracted.txt")
    if a.captions: z.write(a.captions, "03-lecture-captions.txt")
    for m in used: z.write(os.path.join(a.media, m), "media/" + m)
print(f"{a.out}: brief + {len(cards)} cards + extract" + (" + captions" if a.captions else "") + f" + {len(used)} media")
