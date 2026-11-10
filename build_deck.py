# -*- coding: utf-8 -*-
"""Package cards.json into an .apkg. Packaging only - no authoring decisions here.

new lecture : build_deck.py --cards cards.json --media media --out X.apkg --registry registry.md --lines lines.json --scope scope.json
rebuild     : build_deck.py --cards cards.json --media media --out X.apkg --deck-id N --prev old-cards.json --lines lines.json --scope scope.json
check only  : add --check (runs every gate, builds nothing)

Gates, all blocking: text hygiene, cloze syntax, 60% rule, hints, media, duplicates,
slide order, card lints, slide-text coverage (coverage.py), and note-type changes
against --prev. A blocking lint is overridden per card, never globally:
    "lint_ok": {"long": "ordered walkthrough - order is the fact"}
    "order":   "is-before-does"        (a card deliberately placed ahead of its slide)
Fix the card, never the threshold. NEVER edit the CSS, templates or model ids below.
"""
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
ap.add_argument("--prev", help="the previous cards.json of this deck: prints the Anki delete search and blocks note-type changes")
ap.add_argument("--allow-type-change", action="store_true", help="only when Kai has confirmed the deck is NOT yet imported")
ap.add_argument("--lines", help="lines.json from extract.py: turns on the slide-text coverage gate")
ap.add_argument("--scope", help="scope.json: skipped slides/lines with their K/L/N/IO reasons")
ap.add_argument("--coverage-md", default="coverage.md")
ap.add_argument("--io", help="IO_DIR from io_masks.py: adds its image-occlusion notes to this deck")
ap.add_argument("--check", action="store_true", help="run the gates only; build nothing")
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

errors, warnings, overrides = [], [], []
def lint(c, code, msg, block=True):
    """A card-quality finding. Blocking unless the card carries lint_ok[code] with a reason."""
    ok = (c.get("lint_ok") or {}).get(code)
    if ok: overrides.append(f"{c.get('uid')}: {code} allowed - {ok}")
    elif block: errors.append(f"{c.get('uid')}: [{code}] {msg}")
    else: warnings.append(f"{c.get('uid')}: [{code}] {msg}")
seen_uid, seen_first = set(), {}
io_notes = []
if a.io:                                   # image-occlusion notes: pictures are copied into MEDIA_DIR first
    import io_deck
    io_notes = io_deck.notes(a.io, MEDIA_DIR)
used_media, available = {fn for _, _, fn in io_notes}, set(os.listdir(MEDIA_DIR))
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
        lint(c, "long", "over 210 chars - two facts? (an ordered walkthrough needs lint_ok)")

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

# --- card lints: the recall-target and set defects audits kept finding by hand ---
STOP = set("""the a an of and or to in on by for with from is are was were be as at it its that this
which into than then their there these those not no but can may also each such via per between through
during within without where when while because called known named found mainly usually""".split())
SET_WORDS = r"(?:advantage|disadvantage|reason|feature|cause|factor|way|role|function|type|example|challenge|benefit)s?"
UNCUED = re.compile(r"\b(?:one|another|a further|also|partly)\b[^.?!]{0,40}?\b" + SET_WORDS + r"\b", re.I)
HEDGE = re.compile(r"check before trusting|appeared to say|not sure|may be wrong|might be wrong|unverified|i think\b|\bguess", re.I)
def visible(c, k=None):
    """What the learner sees before answering: Basic front, or the cloze with index k blanked."""
    if c["type"] == "basic": return norm(c.get("front", ""))
    t = c["text"]
    for s in cloze_spans(t):
        raw = "{{c%d::%s}}" % (s["index"], s["inner"])
        t = t.replace(raw, " ___ " if s["index"] == k else s["inner"], 1)
    return norm(t)
def words(s): return {w for w in re.findall(r"[a-z][a-z\-]{5,}", norm(s)) if w not in STOP}
cloze_answers = defaultdict(set)
prev_slide = 0
for c in cards:
    uid = c.get("uid")
    answers = []                                         # (index, answer)
    if c["type"] == "basic": answers = [(None, c.get("back", ""))]
    else: answers = [(s["index"], s["inner"]) for s in cloze_spans(c.get("text", ""))]
    for k, ans in answers:
        a_, vis = norm(ans), visible(c, k)
        if a_ in ("yes", "no", "true", "false"): lint(c, "binary", f"answer {a_!r} is a 50% guess")
        if 4 <= len(a_) <= 80 and re.search(r"(?<![a-z])" + re.escape(a_) + r"(?![a-z])", vis):
            lint(c, "leak", f"answer {a_!r} is visible elsewhere on the card")
        else:
            echo = sorted(words(ans) & words(vis))
            if echo: lint(c, "echo", f"answer shares {echo} with the visible text - cover the answer and re-read", block=False)
        if c["type"] == "cloze" and len(a_) >= 4: cloze_answers[a_].add(uid)
    vis_all = norm(c.get("front", "")) if c["type"] == "basic" else norm(plain(c.get("text", "")))
    if UNCUED.search(vis_all): lint(c, "set", "uncued set member ('one/another/also ... X') - name the member or regroup the set")
    if c["type"] == "basic":
        b = c.get("back", "")
        if len(re.split(r"<br\s*/?>", b)) >= 3 or "<li" in b: lint(c, "list", "list on the back - use a grouping cloze or per-member cards")
        if c.get("front", "").count("?") > 1: lint(c, "two-q", "more than one question on the front", block=False)
    else:
        if max((s["index"] for s in cloze_spans(c["text"])), default=1) > 1:
            lint(c, "c2", "uses c2+ - only for independent facts; set members hide together under c1", block=False)
        if re.search(r"\b(?:a|an)\s+(?:<[^>]+>)*\{\{c\d+::", c["text"], re.I):
            lint(c, "article", "a/an directly before a deletion can leak the answer", block=False)
    if HEDGE.search(strip_html(c.get("extra", ""))): lint(c, "hedge", "Extra voices doubt about the card - resolve it or ask Kai; do not ship the doubt")
    m = re.search(r"slides?\s+(\d+)", c.get("source", ""))
    if m and not c.get("order"):
        n = int(m.group(1))
        if n < prev_slide: errors.append(f"{uid}: [order] slide {n} after slide {prev_slide} - cards follow slide order "
                                         f"(set \"order\": \"is-before-does\" or \"overview\" if deliberate)")
        prev_slide = max(prev_slide, n)
    elif c.get("order"): overrides.append(f"{uid}: order - {c['order']}")
for a_, uids in sorted(cloze_answers.items()):
    if len(uids) > 1: warnings.append(f"[dup-answer] {a_!r} is hidden on {sorted(uids)} - same fact twice?")

# --- rebuild diff: what Kai must delete in Anki, and note-type changes that would not import ---
removed, retyped = [], []
if a.prev:
    old = {c["uid"]: c for c in json.load(open(a.prev, encoding="utf-8"))["cards"]}
    new = {c["uid"]: c for c in cards}
    removed = sorted(set(old) - set(new))
    retyped = sorted(u for u in set(old) & set(new) if old[u]["type"] != new[u]["type"])
    if retyped and not a.allow_type_change:
        errors.append(f"note type changed for {retyped}: Anki will not update these on import. Keep the type "
                      f"(question-form cloze), or give a new UID; --allow-type-change only if the deck is not imported")

# --- slide-text coverage gate (PART 00) ---
cov_stats = None
if a.lines:
    import coverage
    rows, cdefects, cov_stats, clines, _ = coverage.check(a.lines, CARDS, a.scope)
    coverage.write_md(a.coverage_md, rows, cdefects, cov_stats, clines, cards)
    errors += [f"[coverage] {d}" for d in cdefects]
else:
    warnings.append("[coverage] NOT RUN - pass --lines lines.json --scope scope.json. Do not call this deck complete.")

print("=" * 72)
print(f"PRE-FLIGHT | {len(cards)} text notes | {len(io_notes)} image-occlusion notes | {len(used_media)} media")
print("=" * 72)
for w in warnings: print("  warn ", w)
for o in overrides: print("  allow", o)
if cov_stats: print("  coverage:", ", ".join(f"{k} {v}" for k, v in sorted(cov_stats.items())), f"-> {a.coverage_md}")
if a.prev:
    print(f"  vs --prev: {len(removed)} removed, {len(retyped)} retyped")
    if removed: print("  DELETE IN ANKI (if the previous build was imported):\n    " + " OR ".join("UID:" + u for u in removed))
if errors:
    for e in errors: print("  ERROR", e)
    raise SystemExit(f"\nBLOCKED: {len(errors)} error(s). Nothing built.")
print("  no blocking errors" + (f" | {len(warnings)} warning(s) to read" if warnings else ""))
if a.check: raise SystemExit(0)

deck = genanki.Deck(ids["deck_id"], doc["deck"])
nb = nc = 0
last_due = {}
for pos, c in enumerate(cards):
    img = f'<img src="{c["image"]}">' if c.get("image") else ""
    if c["type"] == "basic":
        f = [c["front"], c["back"], img, c.get("image_caption",""), c.get("mnemonic",""),
             c.get("extra",""), c["source"], c["uid"]]; m = basic_model; nb += 1
    else:
        f = [c["text"], c.get("extra",""), img, c.get("image_caption",""), c.get("mnemonic",""),
             c["source"], c["uid"]]; m = cloze_model; nc += 1
    deck.add_note(genanki.Note(model=m, fields=list(f), guid=genanki.guid_for(c["uid"]), tags=[], due=(pos + 1) * 1000))  # due follows cards.json, so Anki shows new cards in this order
    sm = re.search(r"slides?\s+(\d+)", c.get("source", ""))
    if sm and not c.get("order"): last_due[int(sm.group(1))] = (pos + 1) * 1000
for i, (slide, note, _) in enumerate(sorted(io_notes, key=lambda t: t[0])):   # an occlusion note follows its slide's text cards
    note.due = max([d for s_, d in last_due.items() if s_ <= slide], default=0) + 1 + i
    deck.add_note(note)
pkg = genanki.Package(deck)
pkg.media_files = sorted(os.path.join(MEDIA_DIR, x) for x in used_media)
pkg.write_to_file(OUT)
lens = sorted(len(plain(c.get("text") or c["front"] + " " + c["back"])) for c in cards)
print(f"\nBuilt {OUT}\n  Basic Rich {nb} | Cloze Rich {nc} | Image Occlusion {len(io_notes)} notes, "
      f"{sum(n.fields[0].count('::image-occlusion') for _, n, _ in io_notes)} masks | media {len(used_media)}")
print(f"  deck_id: {deck_id}  ({'NEW - add to registry.md' if created else 'existing'})")
import statistics
print(f"  median {statistics.median(lens):g} chars (plain text), max {lens[-1]} | notes with an image: {sum(1 for c in cards if c.get('image'))}")
