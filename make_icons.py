#!/usr/bin/env python3
"""Build helper: render the app icon in all standard sizes into an icon-theme tree.

    python3 make_icons.py <jkmon.svg> <jkmon.png> <output dir> <icon name>

Writes <output dir>/<N>x<N>/apps/<name>.png and <output dir>/scalable/apps/<name>.svg.
Sizes are rendered from the SVG (GdkPixbuf, i.e. the python3-gi that the app needs anyway);
if the SVG cannot be rendered, they are scaled down from the 512 px PNG instead.
"""
import shutil
import sys
from pathlib import Path

SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)


def render_gi(svg, png, size, dest):
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    try:
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg), size, size, True)
    except Exception:  # no SVG loader: scale the PNG
        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(png), size, size, True)
    pix.savev(str(dest), "png", [], [])


def render_pil(svg, png, size, dest):
    from PIL import Image
    Image.open(png).convert("RGBA").resize((size, size), Image.LANCZOS).save(dest)


def main(svg, png, out, name):
    svg, png, out = Path(svg), Path(png), Path(out)
    for size in SIZES:
        d = out / f"{size}x{size}" / "apps"
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"{name}.png"
        for render in (render_gi, render_pil):
            try:
                render(svg, png, size, dest)
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            print(f"warning: could not render {size}x{size}", file=sys.stderr)
            if size == 512:
                shutil.copy(png, dest)
    d = out / "scalable" / "apps"
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(svg, d / f"{name}.svg")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
