# anki-tooling

Scripts for turning one lecture into one Anki deck. Clone them; never read them into a chat.

```
git clone --depth 1 -q https://github.com/everythingwasstructured/anki-tooling.git tooling
pip install python-pptx Pillow genanki --break-system-packages -q
```

## Pipeline

```
# TURN 1 (plan chat)
python3 tooling/extract.py LECTURE.pptx ex              # ex/extract_out.txt + ex/lines.json + ex/img/
python3 tooling/render_figures.py LECTURE.pptx figs     # auto crops + figs/_contact.png + figs/figures.json
#   look at _contact.png ONCE, then write figs_spec.json (kept figures, named, each with "shows")
python3 tooling/recrop.py LECTURE.pptx figs_spec.json figs2 --sheet    # confirm the spec reproduces them

# TURN 2 (cards chat) - PPTX re-attached, spec read from the project
python3 tooling/extract.py LECTURE.pptx ex              # regenerates the same line ids
python3 tooling/recrop.py LECTURE.pptx figs_spec.json figs
python3 tooling/prep_media.py SLUG figs media           # figs/media_map.json: fig name -> media filename
python3 tooling/build_deck.py --cards cards.json --media media --out DECK.apkg \
        --registry registry.md --lines ex/lines.json --scope scope.json          # new deck
python3 tooling/make_bundle.py --slug SLUG --cards cards.json --extract ex/extract_out.txt \
        --media media --brief brief.json --out SLUG-audit.zip [--captions captions.txt]

# REBUILD (after an audit, or any later change)
python3 tooling/build_deck.py --cards cards.json --media media --out DECK.apkg --deck-id N \
        --prev old-cards.json --lines ex/lines.json --scope scope.json
```

`--check` on `build_deck.py` runs every gate and builds nothing.

## What each script guarantees

| Script | Guarantee |
|---|---|
| `extract.py` | Every text line of every slide gets an id (`7.3`; notes `N7.2`). Symbol-font characters are mapped, SmartArt is pulled, super/subscripts kept, cropped pictures flagged. Hazards are listed at the end of `extract_out.txt`. |
| `coverage.py` | Every line id is on a card (`"covers"`), or skipped with a K / L / N / IO reason in `scope.json`. A card with no slide line needs `"stressed_quote"`. Writes `coverage.md` with the table and the heading check. |
| `build_deck.py` | Hygiene, cloze syntax, 60% rule, media, duplicates, slide order, card lints, coverage, note-type changes against `--prev`. Sets each note's `due` to its position in `cards.json`, so Anki shows new cards in that order. Prints the Anki delete search for removed UIDs. |
| `recrop.py` | The same figures from the same spec, every time. |
| `io_masks.py`, `io_deck.py` | Occlusion masks from label ink, with checks; native Anki image-occlusion notes merged into the deck. |
| `unpack_deck.py` | Any `.apkg` of a deck (turn 2's, or Kai's own Anki export) back into `cards.json`, edits and line ids included. |
| `anki_feedback.py` | A report from Kai's Anki export: rhythm, each deck, each card design, what he suspended and edited, the costliest cards. |
| `make_bundle.py` | The audit zip, with the fixed brief (`AUDIT-BRIEF.md`) and the author's private fields stripped. |

## cards.json

```json
{"deck": "Lecture title", "cards": [
  {"uid": "slug-s07-thing", "type": "cloze", "text": "… {{c1::answer}} …",
   "source": "slug slide 7", "covers": ["7.3", "7.4"],
   "extra": "", "image": "slug-ab12cd34ef.png", "image_caption": "", "mnemonic": ""},
  {"uid": "slug-s09-what", "type": "basic", "front": "…?", "back": "…",
   "source": "slug slide 9", "covers": ["9.2"]}
]}
```

Optional per-card keys: `"stressed_quote"` (off-slide card: the lecturer's words), `"order"`
(why the card sits out of slide order, e.g. `"is-before-does"`), `"lint_ok": {"code": "reason"}`.

Blocking lints: `leak`, `set`, `list`, `group` (more than two items hidden on one card), `binary`,
`hedge`, `long`, `order`. Warnings to read: `echo`, `dup-answer`, `long-answer`, `article`, `two-q`.

## Never change

The CSS, the two templates and the model ids in `build_deck.py`. Anki treats any change as a
new note type and orphans every card already imported.

## Image occlusion (only where labelling is examined)

```
pip install scipy numpy --break-system-packages -q
python3 tooling/io_masks.py LECTURE.pptx --init > io_spec.json      # candidates; then prune the spec
python3 tooling/io_masks.py LECTURE.pptx io_spec.json io --lines ex/lines.json
#   look at io/_overlay.png once; fix the spec until CHECKS is empty
python3 tooling/build_deck.py ... --io io --scope scope.json,io/io_scope.json
```

`io_masks.py` derives each mask from the label's ink (normal render minus label-blanked render),
cuts the picture from a render with the body text removed, and checks for label ink outside a
mask, overlapping masks and visible text that names a mask. `io_deck.py` holds the
"Image Occlusion (slides)" note type (id 1730406118) and is imported by `build_deck.py --io`.
Checked against `cvsanat1`: the 19 label-box notes come out with the same 106 masks and the
same boxes as the audited deck.
