# -*- coding: utf-8 -*-
"""What Anki says about the generated decks. Run it on Kai's own export; change nothing in Anki.

usage: python3 anki_feedback.py EXPORT.apkg [report.md]
       (Anki: File > Export > deck package .apkg, "include scheduling information" ticked, media unticked)

The report answers, from the review log and card states alone:
  1 settings and rhythm   desired retention, learning steps, days studied, minutes and new cards per day
  2 each deck             cards, suspended, learning repetitions per card, review failures, seconds, minutes per card
  3 each card design      the same measures by cloze size, answer length, card length, image, source
  4 suspended cards       every card Kai suspended by hand, and whether he had even seen it
  5 edited cards          notes changed after import: what Kai rewrites by hand
  6 worst cards           the cards that cost the most time or failed most

Reading it: suspensions and edits are Kai's verdicts on cards; failures and seconds are what
cards cost. A rule earns its place if the cards it prevents are the ones in sections 4 to 6.
Numbers on fewer than about 30 cards are hints, not findings. Never recommend a change to
Anki's settings as fact: show the numbers and point Kai to Anki's own FSRS tools.
"""
import os, re, sys, json, zipfile, sqlite3, tempfile, statistics as st, datetime as dt
from collections import defaultdict, Counter

if len(sys.argv) < 2: sys.exit(__doc__)
OUT = sys.argv[2] if len(sys.argv) > 2 else "anki-feedback.md"
tmp = tempfile.mkdtemp(); z = zipfile.ZipFile(sys.argv[1])
if "collection.anki21b" in z.namelist():
    import zstandard
    raw = zstandard.ZstdDecompressor().stream_reader(z.open("collection.anki21b")).read()
else:
    raw = z.read("collection.anki21" if "collection.anki21" in z.namelist() else "collection.anki2")
dbp = os.path.join(tmp, "col.db"); open(dbp, "wb").write(raw); db = sqlite3.connect(dbp)

GEN = ("Cloze Rich", "Basic Rich")
try:
    decks = {r[0]: r[1].split("\x1f")[-1] for r in db.execute("select id,name from decks")}
    nts = {r[0]: r[1] for r in db.execute("select id,name from notetypes")}
except sqlite3.OperationalError:                         # old schema: names live in col as JSON
    col = db.execute("select decks,models from col").fetchone()
    decks = {int(k): v["name"].split("::")[-1] for k, v in json.loads(col[0]).items()}
    nts = {int(k): v["name"] for k, v in json.loads(col[1]).items()}
notes = {r[0]: dict(mid=r[1], f=r[2].split("\x1f"), mod=r[3]) for r in db.execute("select id,mid,flds,mod from notes")}
cards = {r[0]: dict(nid=r[1], did=r[2], ord=r[3], type=r[4], queue=r[5], lapses=r[6], data=r[7])
         for r in db.execute("select id,nid,did,ord,type,queue,lapses,data from cards")}
rev = [r for r in db.execute("select id,cid,ease,ivl,lastIvl,time,type from revlog order by id") if r[6] in (0, 1, 2, 3) and r[2] > 0]
if not rev: sys.exit("No review history in this export. Re-export with 'include scheduling information' ticked.")

strip = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s.replace("&nbsp;", " "))).strip()
show = lambda s: strip(re.sub(r"\{\{c\d+::(.*?)\}\}", r"[\1]", s, flags=re.S))
day = lambda ms: (dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) - dt.timedelta(hours=4)).date()

def feat(c):
    n = notes[c["nid"]]; nt = nts.get(n["mid"])
    if nt not in GEN: return None
    f = n["f"]; uid = f[-1]
    if nt == "Cloze Rich":
        dels = re.findall(r"\{\{c(\d+)::(.*?)\}\}", f[0], flags=re.S)
        mine = [strip(x) for i, x in dels if int(i) == c["ord"] + 1]
        plain = strip(re.sub(r"\{\{c\d+::(.*?)\}\}", r"\1", f[0], flags=re.S))
        return dict(uid=uid, kind="cloze", n_del=len(mine), hid=sum(map(len, mine)), plen=len(plain), img=bool(f[2].strip()), text=show(f[0]), extra=strip(f[1]))
    return dict(uid=uid, kind="basic", n_del=1, hid=len(strip(f[1])), plen=len(strip(f[0])) + len(strip(f[1])), img=bool(f[2].strip()),
                text=strip(f[0]) + " -> " + strip(f[1]), extra=strip(f[5]))

S = defaultdict(lambda: dict(learn=0, learn_again=0, rev=0, rev_again=0, t=0, n=0, times=[]))
for i, cid, ease, ivl, last, ms, typ in rev:
    s = S[cid]; s["n"] += 1; s["t"] += ms; s["times"].append(ms / 1000)
    if typ == 0: s["learn"] += 1; s["learn_again"] += ease == 1
    if typ == 1: s["rev"] += 1; s["rev_again"] += ease == 1
rows = []
for cid, c in cards.items():
    f = feat(c)
    if not f: continue
    s = S.get(cid) or dict(learn=0, learn_again=0, rev=0, rev_again=0, t=0, n=0, times=[])
    rows.append(dict(f, slug=f["uid"].split("-")[0], deck=decks.get(c["did"], "?"), susp=c["queue"] == -1, lapses=c["lapses"],
                     med=st.median(s["times"]) if s["times"] else None, **{k: s[k] for k in ("learn", "learn_again", "rev", "rev_again", "t", "n")}))
W = []; P = W.append

def line(name, sel):
    seen = [r for r in sel if r["n"]]
    if len(seen) < 8: return
    rv, ra = sum(r["rev"] for r in seen), sum(r["rev_again"] for r in seen)
    P(f"| {name} | {len(sel)} | {100 * sum(r['susp'] for r in sel) / len(sel):.0f}% | {len(seen)} | {sum(r['learn'] for r in seen) / len(seen):.1f} | "
      f"{(f'{100 * ra / rv:.0f}%' if rv >= 20 else '-')} | {st.median(r['med'] for r in seen):.0f} | {sum(r['t'] for r in seen) / 60000 / len(seen):.1f} | "
      f"{sum(r['t'] for r in seen) / 60000 / sum(r['n_del'] for r in seen):.1f} |")
HEAD = "| | cards | suspended | studied | learning reps per card | review failures | median seconds | minutes per card so far | minutes per hidden item |\n|---|---|---|---|---|---|---|---|---|"

# 1 ---------------------------------------------------------------- settings and rhythm
P("# Anki feedback report\n"); P(f"Export: `{os.path.basename(sys.argv[1])}`. {len(rows)} generated cards, {len(rev)} graded answers, "
  f"{day(rev[0][0])} to {day(rev[-1][0])}.\n\n## 1. Settings and rhythm\n")
dr = Counter(json.loads(c["data"]).get("dr") for c in cards.values() if c["data"] and c["data"] not in ("{}", ""))
P(f"- Desired retention stored on the cards: {dict(dr) or 'not FSRS'}")
P(f"- Learning answers: {dict(Counter(('Again' if e == 1 else 'Good/other') for _, _, e, *_r in [r for r in rev if r[6] == 0]))}. "
  f"Most common next steps: {Counter(r[3] for r in rev if r[6] == 0).most_common(3)} (negative = seconds)")
tt = Counter(); tn = Counter()
for r in rev: tt[r[6]] += r[5]; tn[r[6]] += 1
tot = sum(tt.values())
P("- Time split: " + ", ".join(f"{nm} {100 * tt[k] / tot:.0f}%" for k, nm in ((0, "learning new cards"), (2, "relearning lapses"), (1, "spaced reviews"), (3, "cramming"))))
rv = [r for r in rev if r[6] == 1]
P(f"- Spaced reviews passed: {100 * sum(r[2] > 1 for r in rv) / max(1, len(rv)):.0f}% of {len(rv)}; median interval before a review {st.median(r[4] for r in rv) if rv else '-'} days\n")
D = defaultdict(lambda: dict(n=0, t=0, new=0, rev=0, ok=0)); first = set()
for i, cid, ease, ivl, last, ms, typ in rev:
    d = D[day(i)]; d["n"] += 1; d["t"] += ms
    if cid not in first: first.add(cid); d["new"] += 1
    if typ == 1: d["rev"] += 1; d["ok"] += ease > 1
days = sorted(D); span = (days[-1] - days[0]).days + 1
P(f"- Studied {len(days)} of {span} days. Median day {st.median(D[k]['t'] for k in days) / 60000:.0f} min; heaviest {max(D[k]['t'] for k in days) / 60000:.0f} min.")
gaps = [(a, b) for a, b in zip(days, days[1:]) if (b - a).days > 2]
if gaps: P("- Breaks longer than two days: " + "; ".join(f"{a} to {b}" for a, b in gaps))
P("\n| day | answers | minutes | new cards | reviews | passed |\n|---|---|---|---|---|---|")
for k in days:
    d = D[k]; P(f"| {k} | {d['n']} | {d['t'] / 60000:.0f} | {d['new']} | {d['rev']} | {(str(round(100 * d['ok'] / d['rev'])) + '%') if d['rev'] >= 10 else '-'} |")

# 2, 3 ------------------------------------------------------------- decks and designs
P("\n## 2. Each deck\n\n" + HEAD)
for sl in sorted({r["slug"] for r in rows}, key=lambda s: min(c for c, x in cards.items() if (feat(x) or {}).get("uid", "").startswith(s + "-"))):
    line(sl, [r for r in rows if r["slug"] == sl])
P("\n## 3. Each card design\n\n" + HEAD)
X = rows
for nm, fn in (("Basic", lambda r: r["kind"] == "basic"), ("Cloze, 1 hidden item", lambda r: r["kind"] == "cloze" and r["n_del"] == 1),
               ("Cloze, 2 hidden", lambda r: r["kind"] == "cloze" and r["n_del"] == 2), ("Cloze, 3 hidden", lambda r: r["kind"] == "cloze" and r["n_del"] == 3),
               ("Cloze, 4+ hidden", lambda r: r["kind"] == "cloze" and r["n_del"] >= 4),
               ("Answer under 25 characters", lambda r: r["hid"] < 25), ("Answer 25-44", lambda r: 25 <= r["hid"] < 45), ("Answer 45-79", lambda r: 45 <= r["hid"] < 80),
               ("Answer 80+", lambda r: r["hid"] >= 80), ("Card under 90 characters", lambda r: r["plen"] < 90), ("Card 90-129", lambda r: 90 <= r["plen"] < 130),
               ("Card 130-169", lambda r: 130 <= r["plen"] < 170), ("Card 170+", lambda r: r["plen"] >= 170), ("With a figure", lambda r: r["img"]),
               ("No figure", lambda r: not r["img"]), ("Spoken-source cards (-tr-)", lambda r: "-tr-" in r["uid"])):
    line(nm, [r for r in X if fn(r)])

# 4 ---------------------------------------------------------------- suspended
sus = sorted([r for r in rows if r["susp"]], key=lambda r: r["uid"])
whole = {sl for sl in {r["slug"] for r in rows} if all(r["susp"] for r in rows if r["slug"] == sl)}
P(f"\n## 4. Suspended cards\n\n{len(sus)} of {len(rows)} generated cards are suspended ({100 * len(sus) / len(rows):.0f}%). "
  + (f"Whole decks suspended: {', '.join(sorted(whole))}. " if whole else "")
  + f"Of the rest, {sum(1 for r in sus if r['slug'] not in whole and not r['n'])} were suspended without ever being answered.\n")
P("| uid | answers | card |\n|---|---|---|")
for r in sus:
    if r["slug"] not in whole: P(f"| `{r['uid']}` | {r['n']} | {r['text'][:170].replace('|', '/')} |")

# 5 ---------------------------------------------------------------- edited after import
P("\n## 5. Notes edited after import\n\nThe current text is shown. What it was before is in the saved `cards.json`.\n")
by = defaultdict(list)
for nid, n in notes.items():
    if nts.get(n["mid"]) in GEN: by[n["f"][-1].split("-")[0]].append(n)
P("| uid | edited | card now | Extra now |\n|---|---|---|---|")
for sl, ns in by.items():
    base = st.mode([n["mod"] // 600 for n in ns]) * 600
    for n in sorted([n for n in ns if n["mod"] > base + 3600], key=lambda n: n["mod"]):
        cloze = nts[n["mid"]] == "Cloze Rich"
        body = show(n["f"][0]) if cloze else strip(n["f"][0]) + " -> " + strip(n["f"][1])
        P(f"| `{n['f'][-1]}` | {dt.datetime.fromtimestamp(n['mod'], dt.timezone.utc):%d %b} | {body[:170].replace('|', '/')} | {strip(n['f'][1] if cloze else n['f'][5])[:90].replace('|', '/')} |")

# 6 ---------------------------------------------------------------- worst cards
P("\n## 6. The 40 most expensive cards still in play\n\n| uid | answers | failed | minutes | card |\n|---|---|---|---|---|")
for r in sorted([r for r in rows if not r["susp"] and r["n"] >= 4], key=lambda r: -r["t"])[:40]:
    P(f"| `{r['uid']}` | {r['n']} | {r['learn_again'] + r['rev_again']} | {r['t'] / 60000:.1f} | {r['text'][:150].replace('|', '/')} |")
open(OUT, "w", encoding="utf-8").write("\n".join(W) + "\n")
print(f"{len(rows)} generated cards, {len(rev)} answers -> {OUT}")
