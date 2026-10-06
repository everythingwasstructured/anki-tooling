# -*- coding: utf-8 -*-
"""Package cards.json into an .apkg. Packaging only - no authoring decisions here."""
import os, json, re, random
from collections import defaultdict
import genanki

import argparse, sys
ap = argparse.ArgumentParser(description="Build an Anki deck from cards.json")
ap.add_argument("--cards", required=True)
ap.add_argument("--media", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--deck-id", type=int)
ap.add_argument("--registry")
a = ap.parse_args()
CARDS, MEDIA_DIR, OUT = a.cards, a.media, a.out

MODEL_BASIC_ID = 2016902653
MODEL_CLOZE_ID = 1574784481

used = set()
if a.registry and os.path.exists(a.registry):
    used = {int(x) for x in re.findall(r"deck_id:\s*(\d+)", open(a.registry).read())}
if a.deck_id:
    deck_id, created = a.deck_id, False
else:
    if not a.registry:
        sys.exit("FATAL: new deck needs --registry so an existing deck id is never reused.")
    deck_id = random.randrange(1 << 30, 1 << 31)
    while deck_id in used:
        deck_id = random.randrange(1 << 30, 1 << 31)
    created = True
ids = {"deck_id": deck_id, "model_basic_id": MODEL_BASIC_ID, "model_cloze_id": MODEL_CLOZE_ID}

CSS = """
.card {
  --fg: #1a1a1a; --bg: #ffffff; --muted: #5a5a5a;
  --rule: #d8d8d8; --cloze: #0b62c4; --mark: #fff2a8;
  font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 21px; line-height: 1.5; text-align: left;
  color: var(--fg); background-color: var(--bg);
  max-width: 44em; margin: 0 auto; padding: 16px;
}
.nightMode.card, .night_mode .card, .nightMode .card {
  --fg: #e8e8e8; --bg: #2b2b2b; --muted: #b0b0b0;
  --rule: #4a4a4a; --cloze: #6fb4ff; --mark: #6b5c00;
  color: var(--fg); background-color: var(--bg);
}
.cloze { font-weight: 700; color: var(--cloze); }
mark { background: var(--mark); color: inherit; padding: 0 2px; border-radius: 2px; }
u { text-underline-offset: 3px; }
hr#answer { border: 0; border-top: 2px solid var(--rule); margin: 16px 0; }
.extra { font-size: 17px; color: var(--muted); margin-top: 10px; }
.mnemonic { font-size: 17px; color: var(--muted); font-style: italic; margin-top: 8px; }
.figure { margin-top: 14px; }
.figure img { max-width: 100%; height: auto; border-radius: 4px;
  background: #fff; padding: 6px; }
.caption { font-size: 14px; color: var(--muted); margin-top: 4px; }
.src { display: none; }
"""
BACK_EXTRAS = (
    '{{#Image}}<div class="figure">{{Image}}'
    '{{#ImageCaption}}<div class="caption">{{ImageCaption}}</div>{{/ImageCaption}}'
    '</div>{{/Image}}'
    '{{#Extra}}<div class="extra">{{Extra}}</div>{{/Extra}}'
    '{{#Mnemonic}}<div class="mnemonic">{{Mnemonic}}</div>{{/Mnemonic}}'
    '{{#Source}}<div class="src">{{Source}}</div>{{/Source}}'
)
basic_model = genanki.Model(MODEL_BASIC_ID, "Basic Rich",
    fields=[{"name": n} for n in ["Front","Back","Image","ImageCaption","Mnemonic","Extra","Source","UID"]],
    templates=[{"name": "Card 1", "qfmt": "{{Front}}",
                "afmt": '{{FrontSide}}<hr id="answer">{{Back}}' + BACK_EXTRAS}], css=CSS)
cloze_model = genanki.Model(MODEL_CLOZE_ID, "Cloze Rich",
    fields=[{"name": n} for n in ["Text","Extra","Image","ImageCaption","Mnemonic","Source","UID"]],
    templates=[{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}" + BACK_EXTRAS}],
    model_type=genanki.Model.CLOZE, css=CSS)

doc = json.load(open(CARDS, encoding="utf-8"))
cards = doc["cards"]

def cloze_spans(text):
    spans, i, n = [], 0, len(text)
    while i < n:
        m = re.match(r"\{\{c(\d+)::", text[i:]) if text.startswith("{{c", i) else None
        if not m:
            i += 1; continue
        idx, j = int(m.group(1)), i + m.end()
        depth, start = 1, j
        while j < n and depth:
            if text.startswith("{{", j): depth += 1; j += 2; continue
            if text.startswith("}}", j):
                depth -= 1
                if depth == 0: break
                j += 2; continue
            j += 1
        spans.append({"index": idx, "inner": text[start:j]})
        i = j + 2
    return spans

def strip_html(s): return re.sub(r"<[^>]+>", "", str(s))
def plain(t):
    for _ in range(6):
        t = re.sub(r"\{\{c\d+::(.*?)\}\}", r"\1", t, flags=re.S)
    return strip_html(t)
def norm(s): return re.sub(r"\s+", " ", strip_html(s)).strip().lower().rstrip(".")

errors, warnings = [], []
seen_uid, seen_first = set(), {}
used_media, available = set(), set(os.listdir(MEDIA_DIR))
ALLOWED = r"/?(?:b|i|u|em|strong|br|mark|sub|sup|div|span)\b"

for c in cards:
    uid = c.get("uid") or "<NO UID>"
    if uid in seen_uid: errors.append(f"{uid}: duplicate UID")
    seen_uid.add(uid)
    if not c.get("source"): errors.append(f"{uid}: empty Source")
    first = c.get("text") if c["type"] == "cloze" else c.get("front")
    if not first: errors.append(f"{uid}: empty first field")
    elif first.strip() in seen_first: errors.append(f"{uid}: duplicate first field with {seen_first[first.strip()]}")
    else: seen_first[first.strip()] = uid
    blob = " ".join(str(c.get(k, "")) for k in ("front","back","text","extra","image_caption","mnemonic"))
    if "\n" in blob: errors.append(f"{uid}: raw newline")
    for ch in (" ", "​", "‘", "’", "“", "”"):
        if ch in blob: errors.append(f"{uid}: stray {ch!r}")
    if re.search(r"&(?!(?:amp|lt|gt|nbsp|#\d+);)", blob): errors.append(f"{uid}: unescaped &")
    for m in re.finditer(r"<(?!" + ALLOWED + r")", blob): errors.append(f"{uid}: unescaped <")
    if c["type"] == "cloze":
        t = c["text"]
        if t.count("{{") != t.count("}}"): errors.append(f"{uid}: unbalanced braces")
        spans = cloze_spans(t)
        if not spans: errors.append(f"{uid}: zero deletions")
        idxs = sorted({s["index"] for s in spans})
        if idxs and idxs != list(range(1, len(idxs)+1)): errors.append(f"{uid}: non-contiguous {idxs}")
        total = len(plain(t))
        question_form = bool(re.search(r"\?\s*(?:<br>\s*)*\{\{c1::", t))
        for k in idxs:
            if question_form: break
            d = sum(len(strip_html(s["inner"])) for s in spans if s["index"] == k)
            if d / total > 0.60: errors.append(f"{uid}: c{k} deletes {d/total:.0%}")
        for s in spans:
            if "::" in s["inner"]: errors.append(f"{uid}: hint inside deletion {s['inner']!r}")
            if len(strip_html(s["inner"]).strip()) < 2 and total < 50:
                errors.append(f"{uid}: short deletion in a stem under 50 chars")
    img = c.get("image")
    if img:
        if "/" in img: errors.append(f"{uid}: image must be bare filename")
        if img not in available: errors.append(f"{uid}: missing media {img}")
        used_media.add(img)
    if len(plain(c.get("text") or c.get("front","") + " " + c.get("back",""))) > 210:
        warnings.append(f"{uid}: over 210 chars")

for o in sorted(available - used_media): errors.append(f"unused media: {o}")

by_answer = defaultdict(list)
for c in cards:
    if c["type"] == "basic": by_answer[norm(c["back"])].append(c["uid"])
for ansr, uids in by_answer.items():
    if len(uids) > 1: errors.append(f"identical answer {ansr!r}: {uids}")
basic_terms = {norm(re.sub(r"</?b>", "", m)): c["uid"] for c in cards if c["type"] == "basic"
               for m in re.findall(r"<b>(.*?)</b>", c["back"])}
for c in cards:
    if c["type"] != "cloze": continue
    members = [norm(s["inner"]) for s in cloze_spans(c["text"]) if s["index"] == 1]
    if len(members) >= 3:
        hits = [(m, basic_terms[m]) for m in members if m in basic_terms]
        if hits: errors.append(f"{c['uid']}: grouping-cloze members also carded alone: {hits}")

print("=" * 72)
print(f"PRE-FLIGHT | {len(cards)} notes | {len(used_media)} media")
print("=" * 72)
for w in warnings: print("  warn ", w)
if errors:
    for e in errors: print("  ERROR", e)
    raise SystemExit(f"\nBLOCKED: {len(errors)} error(s). Nothing built.")
print("  no blocking errors")

deck = genanki.Deck(ids["deck_id"], doc["deck"])
nb = nc = 0
for c in cards:
    img = f'<img src="{c["image"]}">' if c.get("image") else ""
    if c["type"] == "basic":
        f = [c["front"], c["back"], img, c.get("image_caption",""), c.get("mnemonic",""),
             c.get("extra",""), c["source"], c["uid"]]; m = basic_model; nb += 1
    else:
        f = [c["text"], c.get("extra",""), img, c.get("image_caption",""), c.get("mnemonic",""),
             c["source"], c["uid"]]; m = cloze_model; nc += 1
    deck.add_note(genanki.Note(model=m, fields=list(f), guid=genanki.guid_for(c["uid"]), tags=[]))
pkg = genanki.Package(deck)
pkg.media_files = sorted(os.path.join(MEDIA_DIR, x) for x in used_media)
pkg.write_to_file(OUT)
lens = sorted(len(plain(c.get("text") or c["front"] + " " + c["back"])) for c in cards)
print(f"\nBuilt {OUT}\n  Basic Rich {nb} | Cloze Rich {nc} | media {len(used_media)}")
print(f"  deck_id: {deck_id}  ({'NEW - add to registry.md' if created else 'existing'})")
print(f"  median {lens[len(lens)//2]} chars, max {lens[-1]}")
