# -*- coding: utf-8 -*-
"""Image-occlusion masks from a lecture's own label text boxes.

step 1  python3 io_masks.py LECTURE.pptx --init > io_spec.json
        Lists every slide that has a picture and short text boxes, with each candidate label.
        EDIT the spec: delete slides and labels that are not wanted. That edit is the authoring.
step 2  python3 io_masks.py LECTURE.pptx io_spec.json IO_DIR [--lines ex/lines.json]
        Writes IO_DIR/io-s<N>.png, io_geom.json, io_scope.json, _overlay.png and prints CHECKS.
step 3  look at IO_DIR/_overlay.png ONCE, fix the spec, re-run until CHECKS is clean.
step 4  build_deck.py ... --io IO_DIR

How the masks are made. Three copies of the deck are rendered: normal, labels blanked, and
"clean" (labels kept, body text removed). A label's mask is the box around its INK, the
pixels that differ between normal and blanked. The shape's stored box is not used: a
two-line label overflows it. The picture on the card is cut from the clean render, so body
text cannot answer a mask.

io_spec.json
  {"slug": "cvsanat1", "dpi": 150, "slides": {
     "12": {"header": "Where is the heart located?",
            "labels": {"14": "Left pleural cavity", "18": "Mediastinum"},   shape id -> label text
            "context": {"7": "Anterior view"}}}}                            left visible, for information
  Per-slide options:
    "labels"   edit a text to correct a spelling: the corrected text is rendered and stored.
               A list splits one multi-line text box into a mask per line; "-" leaves a line
               unmasked:  "32": ["-", "Anterior cusp", "Septal cusp", "Posterior cusp"]
    "blank_text" ["SVC = superior vena cava"]   visible text to remove because it answers a mask
    "crop_in"  [l, t, r, b]   slide inches; default is the pictures plus the masks
    "also_hide" [{"with": "Right ventricle", "box_in": [l,t,r,b]}]   printed text hidden with that mask
    "shown"    {"12": "io-s39"}   a label left VISIBLE here because note io-s39 already tests it in a
               similar view. Move a label from "labels" to "shown" to stop testing it twice.
  REPEATS. The same label often appears on several images. Test it once per distinct view:
  mask it again only where the orientation or format differs (anterior vs posterior, internal vs
  surface, diagram vs scan), or where the same words name a different structure (the anterior
  cusp of the tricuspid vs the mitral valve). --init marks repeats, and step 2 lists every label
  still masked on more than one note. Kai sees that list and decides.
  Labels printed INSIDE a picture have no text box. Add them by hand as their own note:
    "54b": {"slide": 54, "header": "...", "crop_in": [...], "dpi": 300,
            "manual": [{"text": "A (aortic valve site)", "box_in": [l,t,r,b]}], "blank_in": [[l,t,r,b]]}

Hide all, guess one: every mask is its own card and all masks are hidden on each card.
"""
import os, sys, re, json, copy, subprocess
from pptx import Presentation
from pptx.oxml.ns import qn

E = 914400
NOT_LABEL = re.compile(r"\?|\bview\b|=|also called|http|@", re.I)

def grp_tf(g):
    x = g._element.grpSpPr.find(qn("a:xfrm"))
    off, ext, co, ce = (x.find(qn(t)) for t in ("a:off", "a:ext", "a:chOff", "a:chExt"))
    ox, oy, ex, ey = int(off.get("x")), int(off.get("y")), int(ext.get("cx")), int(ext.get("cy"))
    cx, cy, cex, cey = int(co.get("x")), int(co.get("y")), int(ce.get("cx")) or 1, int(ce.get("cy")) or 1
    return lambda X, Y, W, H: (ox + (X - cx) * ex / cex, oy + (Y - cy) * ey / cey, W * ex / cex, H * ey / cey)

def walk(shapes, tfs=()):
    """Every leaf shape with its slide-space box in inches (group transforms applied)."""
    for sh in shapes:
        if sh.shape_type == 6:
            yield from walk(sh.shapes, tuple(tfs) + (grp_tf(sh),))
        else:
            try: g = (sh.left, sh.top, sh.width, sh.height)
            except Exception: continue
            if None in g: continue
            for tf in reversed(tfs): g = tf(*g)
            yield sh, [v / E for v in g]

def text_of(sh):
    return " ".join(sh.text_frame.text.split()) if sh.has_text_frame else ""

def is_pic(sh):
    try: return sh.shape_type == 13
    except Exception: return True

def candidates(slide):
    shs = list(walk(slide.shapes))
    pics = [g for sh, g in shs if is_pic(sh) and g[2] > 1.5]
    labs, ctx = {}, {}
    for sh, g in shs:
        t = text_of(sh)
        if not t or sh.is_placeholder or len(t.split()) > 8: continue
        (ctx if NOT_LABEL.search(t) or t in ("Anterior", "Posterior") else labs)[str(sh.shape_id)] = t
    return pics, labs, ctx

# ---------------------------------------------------------------- step 1: --init
if len(sys.argv) == 3 and sys.argv[2] == "--init":
    prs = Presentation(sys.argv[1]); out = {}; seen = {}
    for i, s in enumerate(prs.slides, 1):
        pics, labs, ctx = candidates(s)
        if pics and labs:
            title = next((text_of(sh) for sh in s.shapes if sh.is_placeholder and "TITLE" in str(sh.placeholder_format.type)), "")
            reps = {k: "also a label on slide " + ", ".join(seen[t.lower()]) + " - same view? then move it to \"shown\"" for k, t in labs.items() if t.lower() in seen}
            for t in labs.values(): seen.setdefault(t.lower(), []).append(str(i))
            out[str(i)] = {"header": title or f"Slide {i}", "labels": labs, "shown": {}, "repeats": reps, "context": ctx}
    json.dump({"slug": "SLUG", "dpi": 150, "slides": out}, sys.stdout, ensure_ascii=False, indent=1)
    sys.exit(0)

args = [x for x in sys.argv[1:] if not x.startswith("--")]
if len(args) < 3:
    sys.exit(__doc__)
import numpy as np
from PIL import Image, ImageChops, ImageDraw
from scipy import ndimage
PPTX, SPECF, OUT = args[:3]
LINES = sys.argv[sys.argv.index("--lines") + 1] if "--lines" in sys.argv else None
spec = json.load(open(SPECF, encoding="utf-8"))
SLUG, DPI = spec["slug"], spec.get("dpi", 150)
work = os.path.join(OUT, "_work"); os.makedirs(work, exist_ok=True)
for f in os.listdir(work):                               # renders from an earlier spec are stale: never reuse them
    if f.endswith(".png"): os.remove(os.path.join(work, f))
for f in os.listdir(OUT):
    if f.startswith("io-s") and f.endswith(".png"): os.remove(os.path.join(OUT, f))
notes = spec["slides"]
auto = {k: v for k, v in notes.items() if "manual" not in v}

def set_text(sh, new):
    runs = [r for p in sh.text_frame.paragraphs for r in p.runs]
    if runs:
        runs[0].text = new
        for r in runs[1:]: r.text = ""

def variant(tag):
    """normal: label spellings corrected. blank: label text emptied. clean: body text emptied."""
    prs = Presentation(PPTX)
    for k, v in auto.items():
        slide = prs.slides[int(k) - 1]; labels = v.get("labels", {})
        for sh, _ in walk(slide.shapes):
            t = text_of(sh)
            if not t: continue
            sid = str(sh.shape_id)
            if sid in labels:
                want = labels[sid]
                if tag == "blank": set_text(sh, "")
                elif isinstance(want, str) and want != t: set_text(sh, want)
            elif tag == "clean":
                body = sh.is_placeholder or "?" in t or (len(t.split()) > 8 and "view" not in t.lower())
                if body or any(b in t for b in v.get("blank_text", [])):
                    set_text(sh, "")
    path = os.path.join(work, tag + ".pptx"); prs.save(path)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", work, path], check=True, capture_output=True)
    return os.path.join(work, tag + ".pdf")

def page(pdf, n, dpi=None):
    dpi = dpi or DPI
    stub = os.path.join(work, f"{os.path.basename(pdf)[:-4]}-s{n}-{dpi}")
    if not os.path.exists(stub + ".png"):
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-f", str(n), "-l", str(n), "-singlefile", pdf, stub], check=True)
    return Image.open(stub + ".png").convert("RGB")

PDF = {t: variant(t) for t in ("normal", "blank", "clean")}
prs = Presentation(os.path.join(work, "normal.pptx"))
geom, checks, sheets = {}, [], []
norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

for k, v in notes.items():
    n = int(v.get("slide", k)); dpi = v.get("dpi", DPI)
    px = lambda b: [int(round(x * dpi)) for x in b]
    if "manual" in v:                                    # labels printed inside the picture
        A = page(PDF["normal"], n, dpi); dr = ImageDraw.Draw(A)
        for b in v.get("blank_in", []): dr.rectangle(px(b), fill="white")
        c = px(v["crop_in"]); boxes = [dict(text=m["text"], box=px(m["box_in"])) for m in v["manual"]]
        img = A.crop(tuple(c))
        if dpi > 150: img = img.resize((img.width * 150 // dpi, img.height * 150 // dpi), Image.LANCZOS)
    else:
        A, B, C = (page(PDF[t], n) for t in ("normal", "blank", "clean"))
        D = np.array(ImageChops.difference(A, B).convert("L")) > 40
        slide = prs.slides[n - 1]; labels = v.get("labels", {})
        shs = {str(sh.shape_id): (sh, g) for sh, g in walk(slide.shapes)}
        labs = [(sid, shs[sid]) for sid in labels if sid in shs]
        for sid in labels:
            if sid not in shs: checks.append(f"s{k}: label id {sid} not found on the slide")
        def rect_of(sh, g):                              # a label rotated ~90 degrees occupies the rotated box
            if 45 < (sh.rotation % 180) < 135:
                cx, cy = g[0] + g[2] / 2, g[1] + g[3] / 2; g = [cx - g[3] / 2, cy - g[2] / 2, g[3], g[2]]
            return (max(0, int(g[0] * dpi) - 3), max(0, int(g[1] * dpi) - 3), int((g[0] + g[2]) * dpi) + 3, int((g[1] + g[3]) * dpi) + 3)
        rects = [rect_of(sh, g) for _, (sh, g) in labs]
        comp, _ = ndimage.label(ndimage.binary_dilation(D, structure=np.ones((19, 9))))
        owner = {}
        for i, (x0, y0, x1, y1) in enumerate(rects):
            for cid in np.unique(comp[y0:y1, x0:x1]):
                if cid: owner.setdefault(int(cid), []).append(i)
        ys, xs = np.nonzero(D); cs = comp[ys, xs]
        pix = {i: [] for i in range(len(rects))}
        for cid, idx in owner.items():
            m = cs == cid; py, pxs = ys[m], xs[m]
            if len(idx) == 1: pix[idx[0]].append((py, pxs)); continue
            d = np.stack([np.hypot(np.maximum(0, np.maximum(rects[i][0] - pxs, pxs - rects[i][2])),
                                   np.maximum(0, np.maximum(rects[i][1] - py, py - rects[i][3]))) for i in idx])
            win = d.argmin(axis=0)
            for j, i in enumerate(idx): pix[i].append((py[win == j], pxs[win == j]))
        boxes, exempt = [], []
        for i, (sid, (sh, g)) in enumerate(labs):
            x0, y0, x1, y1 = rects[i]; w, h = x1 - x0, y1 - y0
            if 45 < (sh.rotation % 180) < 135:
                band = (x0 - 12, x1 + 12, y0 - 12, y1 + 12)
            else:                                        # text overflows downwards; re-routed leader lines run sideways
                band = (x0 - 12, x1 + 12, y0 - 12, y1 + max(h, 30) * 1.6)
            kept = [(py[m], q[m]) for py, q in pix[i] for m in [(q >= band[0]) & (q <= band[1]) & (py >= band[2]) & (py <= band[3])]]
            if not kept or not sum(len(p[0]) for p in kept):
                checks.append(f"s{k}: NO INK for label {labels[sid]!r} - is it really a text box on this slide?"); continue
            py = np.concatenate([p[0] for p in kept]); q = np.concatenate([p[1] for p in kept])
            want = labels[sid]
            if isinstance(want, list):                   # one text box, one mask per line
                rows = np.unique(py); groups = [[rows[0]]]
                for r in rows[1:]: (groups[-1].append(r) if r - groups[-1][-1] <= 6 else groups.append([r]))
                if len(groups) != len(want):
                    checks.append(f"s{k}: label {sid} has {len(groups)} ink lines but the spec lists {len(want)}"); continue
                for grp, name in zip(groups, want):
                    m = (py >= grp[0]) & (py <= grp[-1])
                    if name == "-":                      # a line left visible on purpose
                        exempt.append([int(q[m].min()) - 3, int(grp[0]) - 3, int(q[m].max()) + 3, int(grp[-1]) + 3]); continue
                    boxes.append(dict(id=sid, text=name, box=[int(q[m].min()) - 3, int(grp[0]) - 3, int(q[m].max()) + 3, int(grp[-1]) + 3]))
            else:
                boxes.append(dict(id=sid, text=want, box=[int(q.min()) - 3, int(py.min()) - 3, int(q.max()) + 3, int(py.max()) + 3]))
        for e in v.get("also_hide", []):
            boxes.append(dict(text=e["with"], box=px(e["box_in"]), group=e["with"]))
        if v.get("crop_in"): c = px(v["crop_in"])
        else:
            pics = [g for sh, g in walk(slide.shapes) if is_pic(sh) and g[2] > 1.5]
            c = [min([b["box"][0] for b in boxes] + [int(g[0] * dpi) for g in pics]) - 10,
                 min([b["box"][1] for b in boxes] + [int(g[1] * dpi) for g in pics]) - 10,
                 max([b["box"][2] for b in boxes] + [int((g[0] + g[2]) * dpi) for g in pics]) + 10,
                 max([b["box"][3] for b in boxes] + [int((g[1] + g[3]) * dpi) for g in pics]) + 10]
        c = [max(0, c[0]), max(0, c[1]), min(A.width, c[2]), min(A.height, c[3])]
        img = C.crop(tuple(c))
        # CHECK 1: label ink left showing outside every mask
        cover = np.zeros_like(D)
        # a leader line re-routes by a pixel or two when its label is blanked; that fringe is not label text.
        # It sits beside ink that is still dark in the blanked render, so ink near such pixels is not counted.
        near_line = ndimage.binary_dilation(np.array(B.convert("L")) < 110, iterations=3)
        for a_ in boxes:                                 # stacked labels: padding makes neighbours touch; split the difference
            for b_ in boxes:
                A_, B_ = a_["box"], b_["box"]
                if a_ is not b_ and A_[0] < B_[2] and B_[0] < A_[2] and A_[1] < B_[1] <= A_[3] <= B_[3] and A_[3] - B_[1] <= 10:
                    mid = (A_[3] + B_[1]) // 2; A_[3] = mid; B_[1] = mid + 1
        for bx in [b["box"] for b in boxes] + exempt: cover[max(0, bx[1]):bx[3] + 1, max(0, bx[0]):bx[2] + 1] = True
        for b in boxes:
            x0, y0, x1, y1 = b["box"]; reg = np.zeros_like(D); reg[max(0, y0 - 40):y1 + 41, max(0, x0 - 25):x1 + 26] = True
            left = int((D & reg & ~cover & ~near_line).sum())
            if left > 15: checks.append(f"s{k}: {left}px of label ink show outside the mask for {b['text']!r}")
        # CHECK 2: visible text inside the crop that names a mask
        masked = {norm(b["text"]) for b in boxes}
        clean = Presentation(os.path.join(work, "clean.pptx")).slides[n - 1]
        for sh, g in walk(clean.shapes):
            t = text_of(sh)
            if not t or str(sh.shape_id) in labels: continue
            inside = g[0] * dpi < c[2] and (g[0] + g[2]) * dpi > c[0] and g[1] * dpi < c[3] and (g[1] + g[3]) * dpi > c[1]
            hit = [m for m in masked if m and re.search(r"\b" + re.escape(m) + r"\b", norm(t))]
            if inside and hit: checks.append(f"s{k}: visible text {t!r} names the mask {hit} - add it to blank_text, mask it, or change crop_in")
    for i, a_ in enumerate(boxes):
        for b_ in boxes[i + 1:]:
            A_, B_ = a_["box"], b_["box"]
            if not (A_[2] < B_[0] or B_[2] < A_[0] or A_[3] < B_[1] or B_[3] < A_[1]) and a_.get("group") != b_["text"] and b_.get("group") != a_["text"]:
                checks.append(f"s{k}: masks overlap: {a_['text']!r} and {b_['text']!r}")
    cw, ch = c[2] - c[0], c[3] - c[1]
    for b in boxes:
        x0, y0, x1, y1 = b["box"]
        b["norm"] = [round((x0 - c[0]) / cw, 4), round((y0 - c[1]) / ch, 4), round((x1 - x0) / cw, 4), round((y1 - y0) / ch, 4)]
    img.save(os.path.join(OUT, f"io-s{k}.png"))
    geom[k] = dict(slide=n, header=v.get("header", f"Slide {n}"), crop=c, boxes=boxes)
    ov = img.copy(); dr = ImageDraw.Draw(ov); W2, H2 = ov.size
    for b in boxes:
        x, y, w, h = b["norm"]; dr.rectangle([x * W2, y * H2, (x + w) * W2, (y + h) * H2], outline=(255, 0, 255), width=3)
    dr.text((6, 6), f"io-s{k}", fill=(255, 0, 255)); ov.thumbnail((760, 620)); sheets.append(ov)
    print(f"  io-s{k}: {len(boxes)} masks")

json.dump({"slug": SLUG, "notes": geom}, open(os.path.join(OUT, "io_geom.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
if LINES:                                                # which line ids these notes carry, for scope.json
    lines = json.load(open(LINES, encoding="utf-8"))["lines"]; prs0 = Presentation(PPTX); sc = {}
    for k, v in auto.items():
        owner = {}                                       # (shape name, paragraph text) -> shape id; names alone are not unique
        for sh, _ in walk(prs0.slides[int(k) - 1].shapes):
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    owner.setdefault((sh.name, " ".join(p.text.split())), str(sh.shape_id))
        for l in lines:
            sid = owner.get((l["shape"], l["text"]))
            if l["slide"] != int(k) or l["kind"] == "notes" or sid is None: continue
            if sid in v.get("labels", {}): sc[l["id"]] = f"IO io-s{k}"
            elif sid in v.get("shown", {}): sc[l["id"]] = f"IO {v['shown'][sid]} (tested there; shown as context on io-s{k})"
    json.dump({"skip_lines": sc}, open(os.path.join(OUT, "io_scope.json"), "w"), indent=0)
    print(f"  io_scope.json: {len(sc)} line ids carried by image occlusion (pass it to --scope after scope.json, comma-separated)")
cols = 3; rows_ = (len(sheets) + cols - 1) // cols
sheet = Image.new("RGB", (cols * 770, rows_ * 630), "white")
for i, s in enumerate(sheets): sheet.paste(s, ((i % cols) * 770 + 5, (i // cols) * 630 + 5))
sheet.save(os.path.join(OUT, "_overlay.png"))
total = sum(len(g["boxes"]) for g in geom.values())
print(f"{len(geom)} notes, {total} masks -> {OUT}   (look at _overlay.png once)")
where = {}
for k, g in geom.items():
    for b in g["boxes"]:
        if not b.get("group"): where.setdefault(" ".join(b["text"].lower().split()), []).append(f"io-s{k}")
reps = {t: v for t, v in where.items() if len(set(v)) > 1}
print(f"REPEATS ({len(reps)} labels masked on more than one note, {sum(len(set(v)) - 1 for v in reps.values())} extra cards) - "
      f"keep a repeat only where the view differs or the words name a different structure; otherwise move it to \"shown\"")
for t, v in sorted(reps.items(), key=lambda x: -len(x[1])): print(f"  {t}: {', '.join(dict.fromkeys(v))}")
print(f"CHECKS ({len(checks)})"); [print("  " + c_) for c_ in checks]
