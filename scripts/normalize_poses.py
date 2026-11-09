"""Puts every pose on the same square canvas so the app can show them in one box.

Each pose is trimmed to its visible pixels, scaled so the character is FIGURE_HEIGHT
tall (or narrower if a wide pose would overflow), then placed feet-down on the bottom
edge and pinned to the LEFT edge. The art faces right and the app mirrors it, so on
screen every character stands at the same spot on the right with props (carts) to
its left.

Run after adding images:  python scripts/normalize_poses.py
Safe to re-run: already-normalized files come out the same.
"""
import glob
import os

from PIL import Image

CANVAS = 440
MARGIN = 12
FIGURE_HEIGHT = CANVAS - 2 * MARGIN
MAX_WIDTH = CANVAS - 2 * MARGIN

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

for path in sorted(glob.glob(os.path.join(root, '*', '[0-9]*-*.png'))):
    im = Image.open(path).convert('RGBA')
    bbox = im.getchannel('A').point(lambda v: 255 if v > 16 else 0).getbbox()
    if not bbox:
        continue
    figure = im.crop(bbox)
    scale = min(FIGURE_HEIGHT / figure.height, MAX_WIDTH / figure.width)
    size = (round(figure.width * scale), round(figure.height * scale))
    if size != figure.size:
        figure = figure.resize(size, Image.LANCZOS)
    canvas = Image.new('RGBA', (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(figure, (MARGIN, CANVAS - MARGIN - figure.height), figure)
    canvas.save(path, optimize=True)
    print(f'{os.path.relpath(path, root)}  {im.size} -> {canvas.size}')
