"""Replace mockup labels: erase text inside a box (per-column vertical interpolation
from the rows just above/below), then draw new text with Inter at the measured
cap height, colour and left/centre alignment."""
import json, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
FONTS = "/usr/share/fonts/opentype/inter/Inter-{}.otf"

def lum(a): return a[..., 0]*0.299 + a[..., 1]*0.587 + a[..., 2]*0.114

def edit(im, e):
    x0, y0, x1, y1 = e["box"]
    a = np.asarray(im).astype(float)
    def smooth(row, k=7):                       # kill per-column texture noise
        pad = np.pad(row, ((k//2, k//2), (0, 0)), mode="edge")
        return np.stack([pad[i:i+len(row)] for i in range(k)]).mean(0)
    top = smooth(a[y0-2:y0, x0:x1].mean(0)); bot = smooth(a[y1:y1+2, x0:x1].mean(0))
    region = a[y0:y1, x0:x1]
    bg_est = np.stack([top*(1-t)+bot*t for t in np.linspace(0, 1, y1-y0)])
    diff = np.abs(lum(region) - lum(bg_est))
    mask = diff > e.get("thr", 40)
    ys, xs = np.nonzero(mask)
    tx0, ty0, ty1 = x0+xs.min(), y0+ys.min(), y0+ys.max()
    tx1 = x0+xs.max()
    sel = region[mask]; strong = diff[mask] >= np.percentile(diff[mask], 85)
    color = tuple(int(c) for c in e.get("color") or sel[strong].mean(0))
    a[y0:y1, x0:x1] = bg_est
    out = Image.fromarray(a.clip(0, 255).astype("uint8"))
    if not e["text"]:                         # erase-only edit (stray mockup glyph)
        return out, dict(old=[int(tx0), int(ty0), int(tx1), int(ty1)], erased=True)
    d = ImageDraw.Draw(out)
    cap = e.get("cap") or (ty1 - ty0 + 1)   # measured ink height of the old label
    ref = e.get("ref") or e["old"]
    size = e.get("size") or 4.0
    while True:
        f = ImageFont.truetype(FONTS.format(e.get("weight", "Regular")), size)
        bb = d.textbbox((0, 0), ref, font=f)
        if e.get("size") or bb[3]-bb[1] >= cap: break
        size += 0.25
    hb = d.textbbox((0, 0), ref, font=f)
    y = ty0 - hb[1]
    w = d.textlength(e["text"], font=f)
    while e.get("maxw") and w > e["maxw"]:
        size -= 0.25
        f = ImageFont.truetype(FONTS.format(e.get("weight", "Regular")), size)
        w = d.textlength(e["text"], font=f)
        hb = d.textbbox((0, 0), ref, font=f)
        y = ty1 - hb[3]                      # keep the baseline when shrinking
    align = e.get("align", "left")
    x = tx0 if align == "left" else ((tx0+tx1)/2 - w/2 if align == "center" else tx1 - w)
    # Draw at 4x and downsample: PIL's hinting at ~10px gives uneven letter spacing.
    k = 4
    big = ImageFont.truetype(FONTS.format(e.get("weight", "Regular")), size * k)
    W, H = int(w * k) + 8 * k, int(size * 2 * k)
    layer = Image.new("L", (W, H), 0)
    ImageDraw.Draw(layer).text((4 * k, 0), e["text"], font=big, fill=255)
    layer = layer.resize((W // k, H // k), Image.LANCZOS)
    ox, oy = int(round(x)) - 4, int(round(y))
    out.paste(Image.new("RGB", layer.size, color), (ox, oy), layer)
    return out, dict(old=[int(tx0), int(ty0), int(tx1), int(ty1)], size=size, color=color, width=w)

if __name__ == "__main__":
    src, spec, dst = sys.argv[1:4]
    im = Image.open(src).convert("RGB")
    for e in json.load(open(spec)):
        im, info = edit(im, e)
        print(e["text"], info)
    im.save(dst, optimize=True)
