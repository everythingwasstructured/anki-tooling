# -*- coding: utf-8 -*-
"""Extract a lecture deck ONCE: readable text for the plan, plus lines.json for coverage.

usage: python3 extract.py LECTURE.pptx OUT_DIR
writes OUT_DIR/extract_out.txt   every slide, every text line with its id, e.g. [7.3]
       OUT_DIR/lines.json        the same lines as data; coverage.py and build_deck.py read it
       OUT_DIR/img/              every embedded picture, plus manifest.json

Every text line of every slide gets a stable id SLIDE.K (title, bullets, text boxes, labels,
grouped shapes, table cells, SmartArt). Speaker-note lines get N<SLIDE>.K. Nothing is
filtered. The plan cites these ids and every card lists the ids it covers.

Hazards handled here, so nobody has to remember to look for them:
  - Symbol-font characters (private-use area) are mapped to real Greek letters and arrows.
    Anything unmapped is printed as a visible marker and listed under HAZARDS, never dropped.
  - SmartArt text is pulled from the diagram part.
  - Superscript and subscript runs are kept as <sup>/<sub>.
  - Pictures cropped inside PowerPoint are flagged with their crop.
  - Charts, OLE objects and linked pictures are flagged.
"""
import os, sys, re, json, hashlib
from pptx import Presentation
from pptx.util import Emu
from lxml import etree

if len(sys.argv) != 3:
    sys.exit("usage: python3 extract.py LECTURE.pptx OUT_DIR")
SRC, OUT = sys.argv[1], sys.argv[2]
IMGDIR = os.path.join(OUT, "img")
os.makedirs(IMGDIR, exist_ok=True)

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
DGM = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Symbol font: private-use code point = 0xF000 + the Symbol-encoding byte.
SYMBOL = {0x61: "α", 0x62: "β", 0x67: "γ", 0x64: "δ", 0x65: "ε", 0x6B: "κ", 0x6C: "λ", 0x6D: "μ",
          0x70: "π", 0x72: "ρ", 0x73: "σ", 0x74: "τ", 0x71: "θ", 0x77: "ω", 0x66: "φ", 0x63: "χ",
          0x79: "ψ", 0x7A: "ζ", 0x68: "η", 0x44: "Δ", 0x57: "Ω", 0x53: "Σ", 0xAD: "↑", 0xAF: "↓",
          0xAE: "→", 0xAC: "←", 0xAB: "↔", 0xDE: "⇒", 0xB3: "≥", 0xA3: "≤", 0xB1: "±", 0xB4: "×",
          0xB0: "°", 0xBB: "≈", 0xB9: "≠", 0xB5: "∝", 0xA5: "∞", 0xB7: "•", 0xD7: "⋅", 0xA2: "′"}
hazards = []
cropped = set()

def fix_pua(text, xml, where):
    """Map private-use characters. Symbol font -> real character; anything else -> marker."""
    if not re.search("[-]", text):
        return text
    font = "Symbol" if "Symbol" in xml else ("Wingdings" if "Wingdings" in xml else "?")
    out = []
    for ch in text:
        cp = ord(ch)
        if 0xE000 <= cp <= 0xF8FF:
            m = SYMBOL.get(cp - 0xF000) if font == "Symbol" else None
            if m:
                out.append(m); hazards.append(f"{where}: Symbol-font U+{cp:04X} read as {m}")
            else:
                out.append(f"⟦U+{cp:04X} {font}⟧")
                hazards.append(f"{where}: UNMAPPED private-use U+{cp:04X} (font {font}) - open the slide render")
        else:
            out.append(ch)
    return "".join(out)

def para_text(p, where):
    """Return (marked, plain) for one paragraph. marked keeps [B]/[I]/[U] and <sup>/<sub>."""
    marked, plain = [], []
    for r in p.runs:
        t = r.text
        if not t:
            continue
        xml = etree.tostring(r._r).decode()
        t = fix_pua(t, xml, where)
        base = r._r.find(f"{{{A}}}rPr")
        base = int(base.get("baseline", "0")) if base is not None and base.get("baseline") else 0
        if base > 0: t = f"<sup>{t}</sup>"
        elif base < 0: t = f"<sub>{t}</sub>"
        if base: hazards.append(f"{where}: super/subscript kept as {t}")
        marks = ("B" if r.font.bold else "") + ("I" if r.font.italic else "") + ("U" if r.font.underline else "")
        marked.append(f"[{marks}]{t}[/{marks}]" if marks else t)
        plain.append(t)
    if not plain:                      # field codes, line breaks only
        t = fix_pua(p.text, "", where)
        return t, t
    return "".join(marked), "".join(plain)

def is_title(sh):
    try:
        t = str(sh.placeholder_format.type); return sh.is_placeholder and "TITLE" in t and "SUBTITLE" not in t
    except Exception:
        return False

def smartart_lines(slide, sh):
    out = []
    rel = sh._element.find(f".//{{{DGM}}}relIds")
    if rel is None:
        return None
    try:
        part = slide.part.related_part(rel.get(f"{{{R}}}dm"))
        root = etree.fromstring(part.blob)
    except Exception:
        return []
    for pt in root.iter(f"{{{DGM}}}pt"):
        if pt.get("type") in ("pres", "parTrans", "sibTrans"):
            continue
        for p in pt.iter(f"{{{A}}}p"):
            t = "".join(x.text or "" for x in p.iter(f"{{{A}}}t")).strip()
            if t: out.append(t)
    return out

prs = Presentation(SRC)
lines, manifest, text_out = [], [], []
notes_count = 0
W = text_out.append
W(f"SLIDE COUNT: {len(prs.slides)}")

def add(slide_no, counter, kind, shape, marked, plain, ind=""):
    plain = " ".join(plain.split())
    if not plain:
        return
    counter[0] += 1
    lid = f"{slide_no}.{counter[0]}"
    lines.append({"id": lid, "slide": slide_no, "kind": kind, "shape": shape, "text": plain})
    W(f"{ind}  [{lid}] {marked.strip()}")

def walk(slide, shapes, slide_no, counter, depth=0):
    ind = "  " * depth
    for sh in shapes:
        name = sh.name
        if hasattr(sh, "shapes"):
            W(f"{ind}<GROUP {name}>")
            walk(slide, sh.shapes, slide_no, counter, depth + 1)
            continue
        where = f"slide {slide_no} {name}"
        if sh.has_text_frame and sh.text_frame.text.strip():
            kind = "title" if is_title(sh) else "text"
            W(f"{ind}<{'TITLE' if kind == 'title' else 'TEXT'} {name}>")
            for p in sh.text_frame.paragraphs:
                m, pl = para_text(p, where)
                add(slide_no, counter, kind, name, "  " * p.level + m, pl, ind)
        if getattr(sh, "has_table", False) and sh.has_table:
            W(f"{ind}<TABLE {name}>")
            for ri, row in enumerate(sh.table.rows):
                for ci, cell in enumerate(row.cells):
                    for p in cell.text_frame.paragraphs:
                        m, pl = para_text(p, where)
                        add(slide_no, counter, "table", f"{name} R{ri}C{ci}", f"R{ri}C{ci}: {m}", pl, ind)
        if "graphicFrame" in sh._element.tag and not getattr(sh, "has_table", False):
            sa = smartart_lines(slide, sh)
            if sa is None:
                W(f"{ind}<GRAPHIC {name} chart/OLE/other - no text extracted; open the render>")
                hazards.append(f"{where}: graphic frame with no extractable text (chart/OLE)")
            else:
                W(f"{ind}<SMARTART {name}>")
                hazards.append(f"{where}: SmartArt, {len(sa)} lines pulled from the diagram part")
                for t in sa:
                    add(slide_no, counter, "smartart", name, t, t, ind)
        try:
            has_img = sh.shape_type == 13 or hasattr(sh, "image")
        except ValueError:
            W(f"{ind}<IMAGE {name} LINKED-NOT-EMBEDDED - use the slide render>")
            hazards.append(f"{where}: linked picture, not embedded"); has_img = False
        if has_img:
            try:
                img = sh.image; blob = img.blob
                fn = f"s{slide_no:02d}-{hashlib.sha1(blob).hexdigest()[:10]}.{img.ext}"
                fp = os.path.join(IMGDIR, fn)
                if not os.path.exists(fp): open(fp, "wb").write(blob)
                pos = (f"L{Emu(sh.left).inches:.1f} T{Emu(sh.top).inches:.1f} "
                       f"W{Emu(sh.width).inches:.1f} H{Emu(sh.height).inches:.1f}")
                crop = [round(getattr(sh, k, 0) or 0, 3) for k in ("crop_left", "crop_top", "crop_right", "crop_bottom")]
                cs = ""
                if any(crop):
                    cs = f" CROPPED l,t,r,b={crop}"
                    cropped.add(slide_no)
                W(f"{ind}<IMAGE {name} file={fn} {pos}{cs}>")
                manifest.append({"slide": slide_no, "file": fn, "bytes": len(blob), "crop": crop})
            except Exception:
                W(f"{ind}<IMAGE {name} NOT EXTRACTABLE (vector or unreadable) - use the slide render>")
                hazards.append(f"{where}: picture not extractable (EMF/WMF?) - use the render")

per_slide = {}
for idx, slide in enumerate(prs.slides, start=1):
    W(f"\n{'=' * 90}\n### SLIDE {idx}  [layout: {slide.slide_layout.name}]")
    counter = [0]
    walk(slide, slide.shapes, idx, counter)
    per_slide[idx] = counter[0]
    chars = sum(len(l["text"]) for l in lines if l["slide"] == idx)
    nk = 0
    if slide.has_notes_slide:
        nps = [p for p in slide.notes_slide.notes_text_frame.paragraphs if p.text.strip()]
        if nps:
            notes_count += 1
            W("  <SPEAKER NOTES - off-slide: context only unless the lecturer marks it important>")
            for p in nps:
                nk += 1
                m, pl = para_text(p, f"slide {idx} notes")
                lines.append({"id": f"N{idx}.{nk}", "slide": idx, "kind": "notes", "shape": "notes",
                              "text": " ".join(pl.split())})
                W(f"    [N{idx}.{nk}] {m}")
    if not nk: W("  <SPEAKER NOTES: none>")
    W(f"  -- slide {idx}: {counter[0]} text lines")
    if chars < 50:
        W(f"  ***FLAG: only {chars} chars of text - picture-only or scanned slide; open the render***")

if cropped:
    hazards.append("pictures cropped inside PowerPoint on slides " + ", ".join(map(str, sorted(cropped)))
                   + " - the files in img/ show more than the slide did; figures come from renders")
W(f"\n\n{'=' * 90}\nHAZARDS ({len(hazards)})")
for h in hazards: W("  " + h)
total = sum(per_slide.values())
W(f"\nTEXT LINES: {total} on {len(prs.slides)} slides | NOTES LINES: {sum(1 for l in lines if l['kind'] == 'notes')}"
  f" on {notes_count} slides | IMAGES: {len(manifest)}")

open(os.path.join(OUT, "extract_out.txt"), "w", encoding="utf-8").write("\n".join(text_out) + "\n")
json.dump({"source": os.path.basename(SRC), "slides": len(prs.slides), "per_slide": per_slide, "lines": lines},
          open(os.path.join(OUT, "lines.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(manifest, open(os.path.join(IMGDIR, "manifest.json"), "w"), indent=1)
print(f"{len(prs.slides)} slides | {total} text lines | {notes_count} slides with notes | "
      f"{len(manifest)} images | {len(hazards)} hazards")
print(f"Read {os.path.join(OUT, 'extract_out.txt')} ONCE. Hazards are listed at its end.")
