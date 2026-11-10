# -*- coding: utf-8 -*-
"""Turn an .apkg back into cards.json, so a deck never has to be retyped or read out of the project.

usage: python3 unpack_deck.py DECK.apkg SLUG [cards.json]

Works on the .apkg that turn 2 built, and on Kai's own Anki export of the deck (File > Export,
deck package). Use Kai's export whenever he has imported the deck: his hand edits are then the
starting text, and the rebuild cannot overwrite them with an older version.

Notes are returned in Anki's new-card order. Each card's covers / order / lint_ok /
stressed_quote come back from the hidden Source field (decks built before Nov 2026 do not
carry them). Suspended cards are listed: Kai suspended them on purpose, so ask before
changing or rebuilding those. Pictures are not unpacked; re-cut them with recrop.py.
"""
import os, re, sys, json, zipfile, sqlite3, tempfile
if len(sys.argv) < 3: sys.exit(__doc__)
APKG, SLUG = sys.argv[1], sys.argv[2]
OUT = sys.argv[3] if len(sys.argv) > 3 else "cards.json"
z = zipfile.ZipFile(APKG); tmp = tempfile.mkdtemp()
if "collection.anki21b" in z.namelist():
    import zstandard
    raw = zstandard.ZstdDecompressor().stream_reader(z.open("collection.anki21b")).read()
else:
    raw = z.read("collection.anki21" if "collection.anki21" in z.namelist() else "collection.anki2")
p = os.path.join(tmp, "c.db"); open(p, "wb").write(raw); db = sqlite3.connect(p)
BASIC, CLOZE = 2016902653, 1574784481
rows = db.execute("select n.id, n.mid, n.flds, min(c.due), min(c.queue), max(c.queue), min(c.type) from notes n "
                  "join cards c on c.nid = n.id where n.mid in (?, ?) group by n.id", (BASIC, CLOZE)).fetchall()
cards, susp, deckname = [], [], None
for nid, mid, flds, due, qmin, qmax, ctype in rows:
    f = flds.split("\x1f")
    if not f[-1].startswith(SLUG + "-"): continue
    if mid == CLOZE: c = dict(uid=f[6], type="cloze", text=f[0], extra=f[1], image=f[2], image_caption=f[3], mnemonic=f[4], source=f[5])
    else: c = dict(uid=f[7], type="basic", front=f[0], back=f[1], image=f[2], image_caption=f[3], mnemonic=f[4], extra=f[5], source=f[6])
    m = re.search(r'src="([^"]+)"', c["image"]); c["image"] = m.group(1) if m else ""
    if " ‖ " in c["source"]:
        c["source"], meta = c["source"].split(" ‖ ", 1); c.update(json.loads(meta))
    c = {k: v for k, v in c.items() if v not in ("", None)}
    if qmin == -1: susp.append(c["uid"])
    cards.append((ctype != 0, due if ctype == 0 else nid, nid, c))     # unseen cards by position, then the rest by creation
cards.sort(key=lambda t: (t[0], t[1], t[2]))
if not cards: sys.exit(f"No notes with UID {SLUG}-... in {APKG}")
try: deckname = next(r[0].split("\x1f")[-1] for r in db.execute("select name from decks where id in (select did from cards where nid=?)", (cards[0][2],)))
except Exception:
    try:
        did = db.execute("select did from cards where nid=?", (cards[0][2],)).fetchone()[0]
        deckname = json.loads(db.execute("select decks from col").fetchone()[0])[str(did)]["name"].split("::")[-1]
    except Exception: deckname = SLUG
json.dump({"deck": deckname, "cards": [c for *_x, c in cards]}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
with_cov = sum(1 for *_x, c in cards if c.get("covers"))
print(f"{len(cards)} notes -> {OUT} | deck name {deckname!r} | {with_cov} carry line ids | {len(susp)} suspended by Kai")
if susp: print("SUSPENDED (Kai's decision - leave them be unless he asks):\n  " + " ".join(susp))
if with_cov < len(cards): print("NOTE: some notes carry no line ids (built before the Source field stored them); the coverage gate cannot run on those.")
