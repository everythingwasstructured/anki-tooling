# -*- coding: utf-8 -*-
"""A one-page "read this first" outline of a lecture, rendered from the plan. No writing involved.

usage: python3 plan_sheet.py plan.md ex/lines.json OUT.html ["Lecture title"]

Kai meets most lecture content for the first time on the cards, and fails them on the first
day. This sheet is the first pass instead: every planned fact, in slide order, under its
slide's heading, readable in a few minutes before the cards are started. It is built only
from plan.md rows (P07 | ENTITY | ASPECT | VALUE | line ids | "quote") and the slide titles in
lines.json, so it costs nothing to make and cannot say anything the plan does not.
"""
import re, sys, json, html
from collections import defaultdict
if len(sys.argv) < 4: sys.exit(__doc__)
plan, lines_path, out = sys.argv[1:4]
title = sys.argv[4] if len(sys.argv) > 4 else "Lecture outline"
lines = json.load(open(lines_path, encoding="utf-8"))["lines"]
heads = defaultdict(list)
for l in lines:
    if l["kind"] == "title": heads[l["slide"]].append(l["text"])
rows, section, exam = defaultdict(list), None, []
for raw in open(plan, encoding="utf-8"):
    if raw.startswith("## "): section = raw[3:].strip().lower(); continue
    cells = [x.strip() for x in raw.strip().strip("|").split("|")]
    if len(cells) >= 5 and re.fullmatch(r"P\d+[a-z]?", cells[0]):
        ids = re.findall(r"N?(\d+)\.\d+", cells[4])
        rows[int(ids[0]) if ids else 0].append(cells)
    elif section == "examinability" and raw.strip().startswith(("-", "*")):
        exam.append(raw.strip().lstrip("-* ").strip())
e = html.escape
H = [f"<!doctype html><meta charset='utf-8'><title>{e(title)}</title>",
     "<style>body{font:16px/1.5 -apple-system,Segoe UI,Arial,sans-serif;max-width:46em;margin:2em auto;padding:0 1em;color:#1a1a1a}"
     "h1{font-size:1.5em}h2{font-size:1.05em;margin:1.4em 0 .3em;border-bottom:1px solid #ccc;padding-bottom:.2em}"
     "ul{margin:.2em 0 .2em 1.1em;padding:0}li{margin:.15em 0}.a{color:#555}.x{background:#fff7d6;padding:.6em .9em;border-radius:6px}"
     "@media(prefers-color-scheme:dark){body{background:#1e1e1e;color:#e6e6e6}.a{color:#aaa}.x{background:#3a3415}h2{border-color:#555}}</style>",
     f"<h1>{e(title)}</h1><p class='a'>Read once before starting the cards. {sum(map(len, rows.values()))} facts, in slide order.</p>"]
if exam:
    H.append("<div class='x'><b>What the lecturer said about the exam</b><ul>" + "".join(f"<li>{e(x)}</li>" for x in exam) + "</ul></div>")
for s in sorted(rows):
    H.append(f"<h2>Slide {s}: {e(' / '.join(heads.get(s, [''])))}</h2><ul>")
    for c in rows[s]:
        H.append(f"<li><b>{e(c[1])}</b> <span class='a'>({e(c[2])})</span>: {e(c[3])}</li>")
    H.append("</ul>")
open(out, "w", encoding="utf-8").write("\n".join(H) + "\n")
print(f"{sum(map(len, rows.values()))} facts on {len(rows)} slides -> {out}")
