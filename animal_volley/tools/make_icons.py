#!/usr/bin/env python3
"""tools/icon/icon_{full,fg,bg}.png(1024px) → 안드로이드/웹 아이콘 생성.

아이콘 원본은 lib/dev/icon.dart가 그린다(웹으로 띄워 1024px로 캡처).
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "android", "app", "src", "main", "res")
src = {k: Image.open(os.path.join(HERE, "icon", f"icon_{k}.png")).convert("RGBA") for k in ("full", "fg", "bg")}

DENS = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def rounded(img, size, radius=0.22):
    im = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=int(size * 4 * radius), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


for name, k in DENS.items():
    d = os.path.join(RES, f"mipmap-{name}")
    os.makedirs(d, exist_ok=True)
    rounded(src["full"], int(48 * k)).save(os.path.join(d, "ic_launcher.png"))
    s = int(108 * k)
    src["fg"].resize((s, s), Image.LANCZOS).save(os.path.join(d, "ic_launcher_foreground.png"))
    src["bg"].convert("RGB").resize((s, s), Image.LANCZOS).save(os.path.join(d, "ic_launcher_background.png"))

d = os.path.join(RES, "mipmap-anydpi-v26")
os.makedirs(d, exist_ok=True)
with open(os.path.join(d, "ic_launcher.xml"), "w") as f:
    f.write('''<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@mipmap/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
''')

web = os.path.join(ROOT, "web")
rounded(src["full"], 32, 0.2).save(os.path.join(web, "favicon.png"))
for s in (192, 512):
    rounded(src["full"], s).save(os.path.join(web, "icons", f"Icon-{s}.png"))
    src["full"].convert("RGB").resize((s, s), Image.LANCZOS).save(os.path.join(web, "icons", f"Icon-maskable-{s}.png"))
print("done")
