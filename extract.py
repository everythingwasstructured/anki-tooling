# -*- coding: utf-8 -*-
import os, hashlib, json
from pptx import Presentation
from pptx.util import Emu

import sys
if len(sys.argv) != 3:
    sys.exit("usage: python3 extract.py LECTURE.pptx OUTPUT_IMAGE_DIR  > extract_out.txt")
SRC, IMGDIR = sys.argv[1], sys.argv[2]
os.makedirs(IMGDIR, exist_ok=True)

prs = Presentation(SRC)
print("SLIDE COUNT:", len(prs.slides))
print("=" * 95)

manifest = []
notes_count = 0

def fmt_runs(para):
    out = []
    for r in para.runs:
        t = r.text
        if not t:
            continue
        marks = ""
        if r.font.bold: marks += "B"
        if r.font.italic: marks += "I"
        if r.font.underline: marks += "U"
        out.append(f"[{marks}]{t}[/{marks}]" if marks else t)
    return "".join(out) if out else para.text

def walk(shapes, slide_no, depth=0):
    lines = []
    for sh in shapes:
        ind = "  " * depth
        name = sh.name
        if hasattr(sh, "shapes"):
            try:
                inner = walk(sh.shapes, slide_no, depth + 1)
                if inner:
                    lines.append(f"{ind}<GROUP {name}>")
                    lines.extend(inner)
                continue
            except Exception:
                pass
        if sh.has_text_frame:
            txts = []
            for p in sh.text_frame.paragraphs:
                t = fmt_runs(p)
                if t.strip():
                    txts.append(f"{ind}  {'  ' * p.level}{t}")
            if txts:
                lines.append(f"{ind}<TEXT {name}>")
                lines.extend(txts)
        if getattr(sh, "has_table", False) and sh.has_table:
            lines.append(f"{ind}<TABLE {name}>")
            for ri, row in enumerate(sh.table.rows):
                cells = [" / ".join(fmt_runs(p) for p in c.text_frame.paragraphs
                                    if p.text.strip()).strip() for c in row.cells]
                lines.append(f"{ind}  R{ri}: " + " | ".join(cells))
        try:
            has_img = sh.shape_type == 13 or hasattr(sh, "image")
        except ValueError:
            lines.append(f"{ind}<IMAGE {name} LINKED-NOT-EMBEDDED - cannot extract; report in handover>")
            has_img = False
        if has_img:
            try:
                img = sh.image
                blob = img.blob
                h = hashlib.sha1(blob).hexdigest()[:10]
                fn = f"s{slide_no:02d}-{h}.{img.ext}"
                fp = os.path.join(IMGDIR, fn)
                if not os.path.exists(fp):
                    open(fp, "wb").write(blob)
                try:
                    pos = (f"L{Emu(sh.left).inches:.1f} T{Emu(sh.top).inches:.1f} "
                           f"W{Emu(sh.width).inches:.1f} H{Emu(sh.height).inches:.1f}")
                except Exception:
                    pos = "pos?"
                lines.append(f"{ind}<IMAGE {name} file={fn} {pos} {len(blob)}B>")
                manifest.append({"slide": slide_no, "file": fn, "bytes": len(blob)})
            except Exception:
                lines.append(f"{ind}<IMAGE {name} NOT EXTRACTABLE (linked or unreadable) - report in handover>")
    return lines

for idx, slide in enumerate(prs.slides, start=1):
    print(f"\n{'='*95}\n### SLIDE {idx}  [layout: {slide.slide_layout.name}]")
    body = walk(slide.shapes, idx)
    for l in body:
        print(l)
    total = sum(len(l) for l in body)
    if slide.has_notes_slide:
        nt = [("    " + fmt_runs(p)) for p in slide.notes_slide.notes_text_frame.paragraphs
              if p.text.strip()]
        if nt:
            notes_count += 1
            print("  <SPEAKER NOTES>")
            for l in nt:
                print(l)
            total += sum(len(x) for x in nt)
        else:
            print("  <SPEAKER NOTES: none>")
    else:
        print("  <SPEAKER NOTES: none>")
    if total < 50:
        print(f"  ***FLAG: only {total} chars extractable — possible image-only/scanned slide***")

json.dump(manifest, open(os.path.join(IMGDIR, "manifest.json"), "w"), indent=1)
print(f"\n\nIMAGES EXTRACTED: {len(manifest)}")
print(f"SLIDES WITH SPEAKER NOTES: {notes_count} / {len(prs.slides)}")
