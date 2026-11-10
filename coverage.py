# -*- coding: utf-8 -*-
"""Slide-text coverage gate (PART 00). Every text line of every slide must be accounted for.

usage: python3 coverage.py lines.json cards.json scope.json [coverage.md]
       python3 coverage.py lines.json plan.md    scope.json [coverage.md]     (turn 1: plan rows instead of cards)

A line is accounted for when one of these holds:
  - a card lists its id in "covers"                       (the normal case; a merged card lists every line it merges)
  - scope.json skips its slide:  "skip_slides": {"2": "K Kai: skip", "1": "N title slide"}
  - scope.json skips the line:   "skip_lines": {"9.6": "L \"That's not really important.\""}
  - it is a slide title and that slide has at least one card  (titles are context; see the heading check)

Reason codes, and nothing else:
  K   Kai said so (say where/when)
  L   the lecturer disowned it - the reason MUST contain the quote in double quotes
  N   not content: title, agenda, divider, reference, admin or learning-objectives slide
  IO  carried by an image-occlusion note, e.g. "IO io-s12"
There is no code for "obvious", "covered in an earlier deck", "illustrative" or "in Extra".

Off-slide rule, checked here too: a card that covers no slide line (only N-lines, or
nothing) must carry "stressed_quote" - the lecturer's own words marking it as important.

scope.json may also carry "titles": ["12.2", ...] for headings that are plain text boxes.
Exit status 1 if anything is unaccounted for. Never filter the lines to make this pass.
"""
import json, re, sys
from collections import defaultdict

CODES = ("K", "L", "N", "IO")

def _plain(c):
    t = c.get("text") or (c.get("front", "") + "  ->  " + c.get("back", ""))
    for _ in range(6):
        t = re.sub(r"\{\{c\d+::(.*?)\}\}", r"[\1]", t, flags=re.S)
    return re.sub(r"<[^>]+>", "", t)

def plan_cards(plan_path):
    """Turn 1: read plan.md rows  `P07 | ENTITY | ASPECT | VALUE | 7.3, 7.4 | "quote"`  as pseudo-cards,
    so coverage is proven before a single card is written."""
    out = []
    for row in open(plan_path, encoding="utf-8"):
        cells = [x.strip() for x in row.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"P\d+[a-z]?", cells[0]):
            out.append({"uid": cells[0], "type": "basic", "front": f"{cells[1]} - {cells[2]}", "back": cells[3],
                        "covers": re.findall(r"N?\d+\.\d+", cells[4]), "stressed_quote": "checked at turn 2"})
    return out

def check(lines_path, cards_path, scope_path):
    data = json.load(open(lines_path, encoding="utf-8"))
    lines = data["lines"]
    cards = plan_cards(cards_path) if cards_path.endswith(".md") else json.load(open(cards_path, encoding="utf-8"))["cards"]
    scope = {}
    for sp in (scope_path or "").split(","):             # e.g. scope.json,io/io_scope.json
        if sp.strip():
            for key, val in json.load(open(sp.strip(), encoding="utf-8")).items():
                if isinstance(val, dict): scope.setdefault(key, {}).update(val)
                else: scope.setdefault(key, []).extend(val)
    skip_slides = {int(k): v for k, v in scope.get("skip_slides", {}).items()}
    skip_lines = scope.get("skip_lines", {})
    titles = set(scope.get("titles", []))
    by_id = {l["id"]: l for l in lines}
    defects, covered = [], defaultdict(list)

    for where, table in (("skip_slides", skip_slides), ("skip_lines", skip_lines)):
        for k, why in table.items():
            code = str(why).split(" ")[0]
            if code not in CODES:
                defects.append(f"{where} {k}: reason must start with one of {CODES}, got {why!r}")
            if code == "L" and str(why).count('"') < 2:
                defects.append(f"{where} {k}: an L (lecturer disowned) reason must quote the lecturer's words")
    for k in skip_lines:
        if k not in by_id: defects.append(f"skip_lines {k}: no such line id")

    for c in cards:
        cov = c.get("covers") or []
        for i in cov:
            if i not in by_id: defects.append(f"{c['uid']}: covers unknown line id {i}")
            else: covered[i].append(c["uid"])
        on_slide = [i for i in cov if i in by_id and by_id[i]["kind"] != "notes"]
        if not on_slide and not c.get("stressed_quote"):
            defects.append(f"{c['uid']}: covers no slide line and has no stressed_quote "
                           f"(off-slide content is a card only when the lecturer marks it important)")

    slides_with_cards = {by_id[i]["slide"] for i in covered if i in by_id}
    rows, stats = [], defaultdict(int)
    for l in lines:
        if l["kind"] == "notes":
            continue
        lid, s = l["id"], l["slide"]
        if lid in covered:
            tgt = " + ".join(dict.fromkeys(covered[lid])); stats["carded"] += 1
        elif lid in skip_lines:
            tgt = skip_lines[lid]; stats[str(tgt).split(" ")[0]] += 1
        elif s in skip_slides:
            tgt = skip_slides[s]; stats[str(tgt).split(" ")[0]] += 1
        elif (l["kind"] == "title" or lid in titles) and s in slides_with_cards:
            tgt = "TITLE (context for this slide's cards)"; stats["title"] += 1
        else:
            tgt = "**NO CARD, NO REASON**"; stats["DEFECT"] += 1
            defects.append(f"line {lid} unaccounted for: {l['text'][:90]}")
        rows.append((lid, l["text"], tgt))
    stats["lines"] = len(rows)
    return rows, defects, dict(stats), lines, cards

def write_md(path, rows, defects, stats, lines, cards):
    by_slide = defaultdict(list)
    idx = {l["id"]: l for l in lines}
    for c in cards:
        for s in sorted({idx[i]["slide"] for i in c.get("covers", []) if i in idx}):
            by_slide[s].append(c)
    out = ["## Slide-text coverage", "",
           f"{stats.get('lines', 0)} lines: " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()) if k != "lines"),
           "", "| Line | Slide text | Card / reason |", "|---|---|---|"]
    out += [f"| {i} | {t[:80].replace('|', '/')} | {g} |" for i, t, g in rows]
    out += ["", "## Heading check", "",
            "Read each slide's heading against its cards. A card that loses what its slide is about is a defect.", ""]
    heads = defaultdict(list)
    for l in lines:
        if l["kind"] == "title": heads[l["slide"]].append(l["text"])
    for s in sorted(by_slide):
        out.append(f"**Slide {s} - {' / '.join(heads.get(s, ['(no title placeholder)']))}**")
        out += [f"- `{c['uid']}` {_plain(c)[:230]}" for c in by_slide[s]] + [""]
    if defects:
        out += ["## DEFECTS", ""] + [f"- {d}" for d in defects]
    open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit("usage: python3 coverage.py lines.json cards.json scope.json [coverage.md]")
    rows, defects, stats, lines, cards = check(*sys.argv[1:4])
    md = sys.argv[4] if len(sys.argv) > 4 else "coverage.md"
    write_md(md, rows, defects, stats, lines, cards)
    print("COVERAGE |", ", ".join(f"{k} {v}" for k, v in sorted(stats.items())), f"| table -> {md}")
    for d in defects: print("  DEFECT", d)
    if defects: sys.exit(f"\nBLOCKED: {len(defects)} coverage defect(s).")
    print("  every line accounted for")
