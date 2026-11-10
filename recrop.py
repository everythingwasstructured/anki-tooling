# -*- coding: utf-8 -*-
"""Re-cut a lecture's figures from a saved spec, so figures never travel between chats.

usage: python3 recrop.py LECTURE.pptx figs_spec.json OUT_DIR [--sheet]

Turn 1 verifies the figures once and saves figs_spec.json to the project (it is text).
Turn 2, and every later rebuild, runs this against the re-attached PPTX and gets the
same figures back. No zip of images is handed from chat to chat.

figs_spec.json is a list. Each entry is one output file:
  {"name": "fig-apex", "slide": 27, "box_in": [0.5, 1.4, 6.2, 6.9]}
optional keys:
  "dpi": 150                      render resolution (default 150; 300 for dense tables)
  "blank": [[l,t,r,b], ...]       boxes in SLIDE inches painted white (stray titles, a visible answer)
  "parts": [{"slide": 34, "box_in": [...]}, {"slide": 38, "box_in": [...]}]
                                  a side-by-side composite; replaces slide/box_in
  "shows": "what the figure shows, written after OPENING it"   (required: no unseen figure is described)
Boxes are inches on the slide, as printed by render_figures.py (figures.json uses the same
"slide"/"box_in" keys, so its entries can be pasted in and renamed).
"""
import os, sys, json, subprocess
from pptx import Presentation
from pptx.util import Emu
from PIL import Image, ImageDraw

args = [x for x in sys.argv[1:] if not x.startswith("--")]
if len(args) != 3:
    sys.exit("usage: python3 recrop.py LECTURE.pptx figs_spec.json OUT_DIR [--sheet]")
PPTX, SPEC, OUT = args
os.makedirs(OUT, exist_ok=True)
work = os.path.join(OUT, "_render"); os.makedirs(work, exist_ok=True)
spec = json.load(open(SPEC, encoding="utf-8"))
prs = Presentation(PPTX)
SW, SH = Emu(prs.slide_width).inches, Emu(prs.slide_height).inches

pdf = os.path.join(work, os.path.splitext(os.path.basename(PPTX))[0] + ".pdf")
if not os.path.exists(pdf):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", work, PPTX],
                   check=True, capture_output=True)
_cache = {}
def page(slide, dpi):
    key = (slide, dpi)
    if key not in _cache:
        stub = os.path.join(work, f"s{slide:02d}-{dpi}")
        if not os.path.exists(stub + ".png"):
            subprocess.run(["pdftoppm", "-f", str(slide), "-l", str(slide), "-r", str(dpi), "-png",
                            "-singlefile", pdf, stub], check=True, capture_output=True)
        _cache[key] = Image.open(stub + ".png").convert("RGB")
    return _cache[key]

def cut(slide, box, dpi, blank):
    im = page(slide, dpi).copy(); W, H = im.size
    px = lambda b: (int(b[0] / SW * W), int(b[1] / SH * H), int(b[2] / SW * W), int(b[3] / SH * H))
    dr = ImageDraw.Draw(im)
    for b in blank: dr.rectangle(px(b), fill="white")
    return im.crop(px(box))

made, problems = [], []
for e in spec:
    name = e.get("name") or os.path.splitext(e["file"])[0]
    if not e.get("shows"): problems.append(f"{name}: no \"shows\" - open the figure and say what it shows")
    dpi, blank = e.get("dpi", 150), e.get("blank", [])
    parts = e.get("parts") or [{"slide": e["slide"], "box_in": e["box_in"]}]
    ims = [cut(p["slide"], p["box_in"], dpi, p.get("blank", blank)) for p in parts]
    if len(ims) > 1:
        h = min(i.height for i in ims)
        ims = [i.resize((int(i.width * h / i.height), h), Image.LANCZOS) for i in ims]
        gap = 16
        im = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) - 1), h), "white")
        x = 0
        for i in ims: im.paste(i, (x, 0)); x += i.width + gap
    else:
        im = ims[0]
    im.save(os.path.join(OUT, name + ".png")); made.append(name + ".png")
    print(f"  {name}.png  {im.size[0]}x{im.size[1]}  " + " + ".join(f"s{p['slide']}" for p in parts))

if "--sheet" in sys.argv:
    CW, CH, cols = 460, 400, 4
    rows = (len(made) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * CW, max(rows, 1) * (CH + 26)), "white"); dr = ImageDraw.Draw(sheet)
    for i, n in enumerate(made):
        th = Image.open(os.path.join(OUT, n)); th.thumbnail((CW - 10, CH - 10))
        x, y = (i % cols) * CW, (i // cols) * (CH + 26)
        sheet.paste(th, (x + 5, y + 22)); dr.text((x + 6, y + 6), n, fill="black")
    sheet.save(os.path.join(OUT, "_contact.png")); print("  contact sheet -> _contact.png")
print(f"{len(made)} figures -> {OUT}")
for p in problems: print("  WARN", p)
