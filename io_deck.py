# -*- coding: utf-8 -*-
"""Native Anki image-occlusion notes from io_masks.py output. Imported by build_deck.py --io IO_DIR.

NEVER edit the model id, the templates or the CSS below: Anki would treat the note type as new.
Each note's UID is <slug>-io-s<N>; its GUID comes from that UID alone, so rebuilds update in place.
"""
import os, json, hashlib, shutil, genanki
IO_MODEL_ID=1730406118
FRONT='''{{#Header}}<div>{{Header}}</div>{{/Header}}
<div style="display: none">{{cloze:Occlusion}}</div>
<div id="err"></div>
<div id="image-occlusion-container">
    {{Image}}
    <canvas id="image-occlusion-canvas"></canvas>
</div>
<script>
try {
    anki.imageOcclusion.setup();
} catch (exc) {
    document.getElementById("err").innerHTML = `Error loading image occlusion. Is your Anki version up to date?<br><br>${exc}`;
}
</script>
'''
BACK=FRONT+'''
<div><button id="toggle">Toggle Masks</button></div>
{{#Back Extra}}<div>{{Back Extra}}</div>{{/Back Extra}}
'''
CSS='''#image-occlusion-canvas {
    --inactive-shape-color: #ffeba2;
    --active-shape-color: #ff8e8e;
    --inactive-shape-border: 1px #212121;
    --active-shape-border: 1px #212121;
    --highlight-shape-color: #ff8e8e00;
    --highlight-shape-border: 1px #ff8e8e;
}
.card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }
.nightMode .card, .night_mode .card { color: #eee; background-color: #2f2f31; }
'''
class IOModel(genanki.Model):
    def to_json(self,*a,**k):
        j=super().to_json(*a,**k); j['originalStockKind']=6; return j
model=IOModel(IO_MODEL_ID,'Image Occlusion (slides)',
  fields=[{'name':n} for n in ['Occlusion','Image','Header','Back Extra','Comments']],
  templates=[{'name':'Image Occlusion','qfmt':FRONT,'afmt':BACK}],css=CSS,model_type=genanki.Model.CLOZE)

def notes(io_dir, media_dir):
    """Return [(slide, note)] and copy each note's picture into media_dir under a namespaced name."""
    d = json.load(open(os.path.join(io_dir, "io_geom.json"), encoding="utf-8"))
    slug, out = d["slug"], []
    for k, g in d["notes"].items():
        src = os.path.join(io_dir, f"io-s{k}.png")
        fn = f"{slug}-io-{hashlib.sha1(open(src, 'rb').read()).hexdigest()[:10]}.png"
        shutil.copy(src, os.path.join(media_dir, fn))
        idx, occ, key, n = {}, "", [], 0
        for b in g["boxes"]:                              # one card per mask; a box with "group" is hidden with that mask
            if b.get("group") in idx: c = idx[b["group"]]
            else:
                n += 1; c = n; idx.setdefault(b["text"], c); key.append(f"c{c}={b['text']}")
            x, y, w, h = b["norm"]
            occ += f"{{{{c{c}::image-occlusion:rect:left={x}:top={y}:width={w}:height={h}:oi=1}}}}<br>"
        uid = f"{slug}-io-s{k}"
        note = genanki.Note(model=model, guid=genanki.guid_for(uid), fields=[
            occ, f'<img src="{fn}">', g.get("header", f"Slide {g['slide']}"), "",
            f"UID: {uid}<br>Source: {slug} slide {g['slide']}<br>" + "; ".join(key)])
        out.append((g["slide"], note, fn))
    return out
