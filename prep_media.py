# -*- coding: utf-8 -*-
import os, sys, hashlib, json, io
from PIL import Image
if len(sys.argv) != 4:
    sys.exit("usage: python3 prep_media.py SLUG SRC_IMAGE_DIR OUT_MEDIA_DIR")
SLUG, SRC, OUT = sys.argv[1:]
os.makedirs(OUT, exist_ok=True)
mapping = {}
for fn in sorted(f for f in os.listdir(SRC)
                 if f.lower().endswith((".png",".jpg",".jpeg",".gif",".bmp",".tif",".tiff",".emf",".wmf"))
                 and not f.startswith("v_")):
    try:
        im = Image.open(os.path.join(SRC, fn)).convert("RGBA")
    except Exception as e:
        print(f"SKIP {fn}: cannot open ({e}) - report in handover"); continue
    bg = Image.new("RGBA", im.size, (255,255,255,255))
    im = Image.alpha_composite(bg, im).convert("RGB")
    w, h = im.size
    if max(w, h) > 1600:
        s = 1600/max(w,h); im = im.resize((int(w*s), int(h*s)), Image.LANCZOS)
    buf = io.BytesIO()
    if fn.lower().endswith(".png"):
        im.save(buf, "PNG", optimize=True); ext = "png"
    else:
        im.save(buf, "JPEG", quality=88, optimize=True); ext = "jpg"
    data = buf.getvalue()
    name = f"{SLUG}-{hashlib.sha1(data).hexdigest()[:10]}.{ext}"
    open(os.path.join(OUT, name), "wb").write(data)
    mapping[fn] = name
    print(f"{fn:34s} -> {name}  {len(data)//1024} KB")
json.dump(mapping, open(os.path.join(SRC, "media_map.json"), "w"), indent=1)
print(f"{len(mapping)} source files -> {len(set(mapping.values()))} unique media files")
