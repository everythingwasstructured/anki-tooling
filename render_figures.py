# -*- coding: utf-8 -*-
"""Cut figures out of a lecture deck deterministically.

Why this exists: cropping by eye off a thumbnail costs several render-look-recrop rounds,
and image reads are the single most expensive thing in a deck build. Every figure's real
position is already in the PPTX, so the crop is computed, not guessed.

What it does:
  1. Renders every slide to PNG via headless LibreOffice -> PDF -> pdftoppm. This also
     recovers EMF/WMF vector art and shape-built diagrams that no image library can open,
     and it bakes in floating text-box labels that the embedded picture files lack.
  2. Builds a bounding box per figure from the shape geometry:
       - a picture inside a PowerPoint GROUP  -> the group's box (the group IS the figure
         plus its labels, which is exactly what you want)
       - an ungrouped picture                 -> its own box, plus any text box within
         LABEL_GAP inches, plus a small margin
       - boxes that overlap or nearly touch are merged, so a row of three MRIs with a
         shared caption comes out as one figure rather than three
  3. Clamps away the title band and footer bar so no crop catches slide furniture.
  4. Writes one contact sheet. VERIFY THAT SHEET, ONCE, then move on.

usage: python3 render_figures.py LECTURE.pptx OUT_DIR [--dpi 150] [--slides 6,7,11-13]
"""
import os, sys, subprocess, argparse, json
from pptx import Presentation
from pptx.util import Emu
from PIL import Image, ImageDraw

MARGIN      = 0.10   # inches added around an ungrouped picture
LABEL_GAP   = 0.45   # a text box this close to a picture is treated as its label
MERGE_GAP   = 0.20   # boxes closer than this are merged into one figure
LABEL_CHARS = 60     # a label is short; longer text is body copy and never joins a figure
LABEL_AREA  = 4.0    # sq. inches; a text box bigger than this is body copy, not a label
TOP_CLAMP   = 0.08   # fraction of slide height reserved for the title band
BOT_CLAMP   = 0.03   # fraction reserved for the footer bar

ap = argparse.ArgumentParser()
ap.add_argument("pptx"); ap.add_argument("outdir")
ap.add_argument("--dpi", type=int, default=150)
ap.add_argument("--slides", help="e.g. 6,7,11-13 — default: every slide holding a picture")
a = ap.parse_args()
os.makedirs(a.outdir, exist_ok=True)
work = os.path.join(a.outdir, "_render"); os.makedirs(work, exist_ok=True)

prs = Presentation(a.pptx)
SW = Emu(prs.slide_width).inches
SH = Emu(prs.slide_height).inches

def boxes_for(slide):
    """Return (picture_boxes, text_boxes, leader_lines) in inches as [x0,y0,x1,y1]."""
    pics, texts, lines = [], [], []
    def walk(shapes, in_group=None):
        for sh in shapes:
            try:
                box = [Emu(sh.left).inches, Emu(sh.top).inches,
                       Emu(sh.left).inches + Emu(sh.width).inches,
                       Emu(sh.top).inches + Emu(sh.height).inches]
            except Exception:
                box = None
            if hasattr(sh, "shapes"):
                # a group: its own box stands in for every figure inside it
                try:
                    walk(sh.shapes, box if box else in_group); continue
                except Exception:
                    pass
            is_pic = False
            try:
                is_pic = sh.shape_type == 13 or hasattr(sh, "image")
            except ValueError:
                is_pic = True          # linked/vector art python-pptx cannot open; render saves it
            except Exception:
                is_pic = False
            if is_pic and box:
                pics.append(list(in_group) if in_group else box)
            elif box and str(getattr(sh, "shape_type", "")).startswith(("LINE", "STRAIGHT", "CONNECTOR")):
                lines.append(box)        # leader lines are glue: they bridge figure to label
            elif box and getattr(sh, "has_text_frame", False):
                t = sh.text_frame.text.strip()
                area = (box[2] - box[0]) * (box[3] - box[1])
                if t and len(t) <= LABEL_CHARS and area <= LABEL_AREA:
                    texts.append(box)
    walk(slide.shapes)
    return pics, texts, lines

def near(a_, b_, gap):
    return not (a_[2] + gap < b_[0] or b_[2] + gap < a_[0] or
                a_[3] + gap < b_[1] or b_[3] + gap < a_[1])

def union(a_, b_):
    return [min(a_[0], b_[0]), min(a_[1], b_[1]), max(a_[2], b_[2]), max(a_[3], b_[3])]

def figures_for(slide):
    pics, texts, lines = boxes_for(slide)
    if not pics: return []
    figs = [[p[0] - MARGIN, p[1] - MARGIN, p[2] + MARGIN, p[3] + MARGIN] for p in pics]
    grew = True                                       # follow leader lines to fixpoint
    while grew:
        grew = False
        for ln in list(lines):
            for i, f in enumerate(figs):
                if near(f, ln, MERGE_GAP):
                    figs[i] = union(f, ln); lines.remove(ln); grew = True; break
            if grew: break
    for t in texts:                                   # pull in nearby labels
        for i, f in enumerate(figs):
            if near(f, t, LABEL_GAP): figs[i] = union(f, t); break
    changed = True                                    # merge until stable
    while changed:
        changed = False
        for i in range(len(figs)):
            for j in range(i + 1, len(figs)):
                if near(figs[i], figs[j], MERGE_GAP):
                    figs[i] = union(figs[i], figs[j]); figs.pop(j); changed = True; break
            if changed: break
    out = []
    for f in figs:
        f = [max(f[0], 0), max(f[1], SH * TOP_CLAMP),
             min(f[2], SW), min(f[3], SH * (1 - BOT_CLAMP))]
        if f[2] - f[0] > 0.8 and f[3] - f[1] > 0.6:   # drop slivers: rules, logos, bullets
            out.append(f)
    for f in out:                                     # over-merge guard
        if (f[2] - f[0]) > SW * 0.85 and (f[3] - f[1]) > SH * 0.80:
            print("  WARN slide figure covers almost the whole slide — check _contact.png")
    return out

want = None
if a.slides:
    want = set()
    for part in a.slides.split(","):
        if "-" in part:
            lo, hi = part.split("-"); want |= set(range(int(lo), int(hi) + 1))
        else: want.add(int(part))

subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", work, a.pptx],
               check=True, capture_output=True)
pdf = os.path.join(work, os.path.splitext(os.path.basename(a.pptx))[0] + ".pdf")

manifest, made = [], []
for idx, slide in enumerate(prs.slides, start=1):
    if want and idx not in want: continue
    figs = figures_for(slide)
    if not figs: continue
    stub = os.path.join(work, "s%02d" % idx)
    subprocess.run(["pdftoppm", "-f", str(idx), "-l", str(idx), "-r", str(a.dpi),
                    "-png", "-singlefile", pdf, stub], check=True, capture_output=True)
    im = Image.open(stub + ".png"); W, H = im.size
    figs.sort(key=lambda f: (round(f[1], 1), f[0]))
    for n, f in enumerate(figs, start=1):
        name = "s%02d-fig%d.png" % (idx, n)
        im.crop((int(f[0] / SW * W), int(f[1] / SH * H),
                 int(f[2] / SW * W), int(f[3] / SH * H))).save(os.path.join(a.outdir, name))
        manifest.append({"file": name, "slide": idx,
                         "box_in": [round(v, 2) for v in f]})
        made.append(name)

json.dump(manifest, open(os.path.join(a.outdir, "figures.json"), "w"), indent=1)

CW, CH = 460, 400
cols = 4; rows = (len(made) + cols - 1) // cols
sheet = Image.new("RGB", (cols * CW, max(rows, 1) * (CH + 26)), "white")
dr = ImageDraw.Draw(sheet)
for i, n in enumerate(made):
    th = Image.open(os.path.join(a.outdir, n)); th.thumbnail((CW - 10, CH - 10))
    x, y = (i % cols) * CW, (i // cols) * (CH + 26)
    sheet.paste(th, (x + 5, y + 22)); dr.text((x + 6, y + 6), n, fill="black")
sheet.save(os.path.join(a.outdir, "_contact.png"))
print("%d figures from %d slides -> %s" % (len(made), len({m['slide'] for m in manifest}), a.outdir))
for m in manifest: print("  %-16s slide %-3d %s" % (m["file"], m["slide"], m["box_in"]))
print("\nVERIFY _contact.png ONCE. Rename kept figures to fig-<meaning>.png, delete the rest,")
print("then run prep_media.py over the surviving files.")
