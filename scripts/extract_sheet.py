"""Cuts a 3x3 pose sheet (white background) into nine transparent pose PNGs.

    python scripts/extract_sheet.py "sheet.png" character-id

Poses must be laid out in the standard order, left to right, top to bottom:
broke-worried, rich-flex, shopping-cart-empty / shopping-cart-full, studying-book,
thinking / piggy-bank-saving, writing-budget-list, celebrating.

How the background goes away:
- White that touches the sheet border is background, and so are floor shadows.
- Enclosed white is background when it's a real gap (cart basket, between the legs,
  inside a curl of hair) and kept when it's drawn white (sneakers, paper, eyes,
  headphones). The rembg anime model plus some colour checks tell them apart.
- Thin white rims and specks along the outline are peeled off.
- Edge pixels are un-blended from white and the outermost pixel is shaved off, so
  nothing light is left around the figure on a dark or coloured screen.
- Floating decorations ("?", "!", sparkles, the cart bubble) are dropped: only the
  figure and whatever touches it is kept.

Check the result on a dark background before committing; odd art can still fool it.

Then run normalize_poses.py and build-manifest.mjs as usual. Needs Pillow, numpy,
scipy and rembg.
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

POSES = [
    'broke-worried', 'rich-flex', 'shopping-cart-empty',
    'shopping-cart-full', 'studying-book', 'thinking',
    'piggy-bank-saving', 'writing-budget-list', 'celebrating',
]
SOFT_LO, SOFT_HI = 6, 60    # edge band: distance from white <= LO clear, >= HI solid
WHITE = 9                   # max distance from the sheet colour that still counts as background
SHADOW = 70                 # light greys the model rejects (floor shadows) up to this distance
BAND = 2                    # px of soft edge next to the background

root = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def subject_mask(rgb):
    from rembg import new_session, remove
    session = new_session('isnet-anime')
    out = remove(Image.fromarray(rgb), session=session, only_mask=True)
    return np.asarray(out.convert('L'), dtype=np.float32) / 255


def enclosed_gaps(img, dist, outside):
    """Background white walled in by the figure: cart baskets, under the cart,
    between the legs, between an arm and the body.

    The model often counts these as subject. They give themselves away by being
    flat sheet-white with no grey outline around them; drawn whites (sneakers,
    paper) are outlined, and eyes sit between black pupils and skin.
    """
    h, w = dist.shape
    pockets = (dist < WHITE + 6) & ~outside
    labels, n = ndi.label(pockets)
    if n == 0:
        return np.zeros_like(pockets)
    idx = range(1, n + 1)
    flat = np.asarray(ndi.mean(dist, labels, idx)) < 3
    size = np.asarray(ndi.sum(pockets, labels, idx))
    sat = img.max(axis=2) - img.min(axis=2)
    val = img.mean(axis=2)
    wire = (sat < 30) & (val > 110) & (val < 235)
    cy, _cx = zip(*ndi.center_of_mass(pockets, labels, idx))
    from_out = np.asarray(ndi.minimum(ndi.distance_transform_edt(~outside), labels, idx))
    gaps = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(labels)):
        if sl is None or size[i] < 40:
            continue
        ys = slice(max(sl[0].start - 3, 0), sl[0].stop + 3)
        xs = slice(max(sl[1].start - 3, 0), sl[1].stop + 3)
        blob = labels[ys, xs] == i + 1
        ring = ndi.binary_dilation(blob, iterations=2) & ~blob
        ring_wire = wire[ys, xs][ring].mean()
        ring_dark = (val[ys, xs][ring] < 90).mean()
        in_head = (cy[i] % (h / 3)) / (h / 3) < 0.42
        # Eyes touch black (pupil, lashes) and skin: leave them.
        r, g, b = (img[ys, xs][ring][:, k] for k in range(3))
        ring_skin = ((r > 170) & (r > g + 12) & (g > b) & (r - b < 140)).mean()
        if in_head and ring_dark >= 0.05 and (ring_skin >= 0.08 or from_out[i] > 40):
            continue
        ring_px = img[ys, xs][ring]
        rv, rs = ring_px.mean(axis=1), ring_px.max(axis=1) - ring_px.min(axis=1)
        outlined = ((rv >= 90) & (rv < 215) & (rs < 35)).mean()
        # White caught inside a curl of hair: walled in by dark strands and their
        # grey anti-aliasing only, no skin, up in the head area.
        if in_head and ring_skin < 0.02 and ring_dark > 0.25 and ring_dark + outlined > 0.75:
            gaps[i + 1] = True
            continue
        # Cart basket: walled in by grey wire, right of the figure and above the
        # feet (sneakers have grey outlines too).
        is_cart = (int(min(cy[i] * 3 // h, 2)) * 3 + int(min(_cx[i] * 3 // w, 2)) in (2, 3)
                   and (_cx[i] % (w / 3)) / (w / 3) > 0.45
                   and ((cy[i] % (h / 3)) / (h / 3) < 0.85 or flat[i]))
        # Anything else: flat white with no grey outline (paper and sneakers have one).
        if (is_cart and ring_wire > 0.4) or (flat[i] and outlined < 0.25):
            gaps[i + 1] = True
    return gaps[labels]


def sheet_alpha(rgb):
    img = rgb.astype(np.float32)
    border = np.concatenate([img[:4].reshape(-1, 3), img[-4:].reshape(-1, 3),
                             img[:, :4].reshape(-1, 3), img[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.abs(img - bg).max(axis=2)
    subject = subject_mask(rgb)
    core = ndi.binary_erosion(subject > 0.5, iterations=4)

    # Background = plain white reachable from the border, plus enclosed white and
    # light grey (floor shadows) that the model says isn't part of the figure.
    white = (dist < WHITE) & ~core
    labels, _ = ndi.label(white)
    edge_ids = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    outside = np.isin(labels, edge_ids[edge_ids > 0])
    sat = img.max(axis=2) - img.min(axis=2)
    shadow = (subject < 0.5) & (dist < SHADOW) & (sat < 24)
    background = outside | (white & (subject < 0.5)) | shadow | enclosed_gaps(img, dist, outside)
    background = ndi.binary_opening(background, iterations=1) | outside

    # Slivers of white between loose hair strands near the outline. The model
    # counts them as subject, but they're just paper showing through.
    pockets = (dist < WHITE) & ~background
    labels, n = ndi.label(pockets)
    if n:
        depth = ndi.distance_transform_edt(pockets)
        thick = ndi.maximum(depth, labels, range(1, n + 1))
        from_out = ndi.distance_transform_edt(~outside)
        closest = ndi.minimum(from_out, labels, range(1, n + 1))
        thick = np.asarray(thick)
        sizes = np.asarray(ndi.sum(pockets, labels, range(1, n + 1)))
        near_edge = (thick <= 5) & (np.asarray(closest) <= 20)
        # Long thin white lines anywhere (gap between collar and neck); eye
        # highlights are round, so they don't count.
        streak = (thick <= 3) & (sizes >= 20) & (sizes / np.maximum(thick, 1) ** 2 > 8)
        candidates = near_edge | streak
        very_dark = img.mean(axis=2) < 120
        # Only between hair strands (darkish, warm or neutral): white details on
        # sneakers or headphones sit inside light or blue/teal outlines and must stay.
        dark = (img.mean(axis=2) < 170) & (img[..., 0] >= img[..., 2] - 4)
        sliver = np.zeros(n + 1, bool)
        for i, sl in enumerate(ndi.find_objects(labels)):
            if sl is None or not candidates[i]:
                continue
            ys = slice(max(sl[0].start - 2, 0), sl[0].stop + 2)
            xs = slice(max(sl[1].start - 2, 0), sl[1].stop + 2)
            blob = labels[ys, xs] == i + 1
            ring = ndi.binary_dilation(blob, iterations=2) & ~blob & ~outside[ys, xs]
            if not ring.any():
                continue
            if near_edge[i] and dark[ys, xs][ring].mean() > 0.7:
                sliver[i + 1] = True
            elif streak[i] and very_dark[ys, xs][ring].mean() > 0.6:
                sliver[i + 1] = True
        background |= sliver[labels]

    # Thin light rims hugging the outline (hair highlights, leftover anti-aliasing)
    # read as a white fringe once the figure sits on a colour. Peel them off, but
    # leave thick white areas like sneaker soles and paper alone.
    light = (dist < 45) & (sat < 70)
    outer = outside.copy()
    for _ in range(2):
        rim = light & ~background & ndi.binary_dilation(outer, iterations=2)
        thin = rim & ~ndi.binary_opening(light & ~background, iterations=2)
        if not thin.any():
            break
        background |= thin
        outer |= thin

    # Last pass on the hair outline: little patches of sheet-white still sitting
    # just inside the edge, next to dark strands.
    edge_band = ~background & (ndi.distance_transform_edt(~background) <= 7)
    patches = (dist < 14) & ~background
    labels, n = ndi.label(patches)
    if n:
        touches_edge = np.zeros(n + 1, bool)
        touches_edge[np.unique(labels[edge_band & patches])] = True
        val = img.mean(axis=2)
        drop = np.zeros(n + 1, bool)
        for i, sl in enumerate(ndi.find_objects(labels)):
            if not touches_edge[i + 1]:
                continue
            ys = slice(max(sl[0].start - 2, 0), sl[0].stop + 2)
            xs = slice(max(sl[1].start - 2, 0), sl[1].stop + 2)
            blob = labels[ys, xs] == i + 1
            if blob.sum() > 400:
                continue
            ring = ndi.binary_dilation(blob, iterations=2) & ~blob & ~background[ys, xs]
            if not ring.any():
                continue
            rv = val[ys, xs][ring]
            # Hair around it, and the model isn't sure it's solid (headphones and
            # hair clips it is sure about).
            if (rv < 110).mean() > 0.2 and subject[ys, xs][blob].mean() < 0.85:
                drop[i + 1] = True
        background |= drop[labels]

    # Everything else is solid, except a thin band next to the background where
    # alpha follows how far the pixel is from white (keeps edges anti-aliased).
    near = ndi.distance_transform_edt(~background)
    soft = np.clip((dist - SOFT_LO) / (SOFT_HI - SOFT_LO), 0, 1)
    alpha = np.where(near <= BAND, np.maximum(soft, (near - 1) / BAND), 1.0)
    alpha[background] = 0
    return alpha.astype(np.float32), bg


def unblend(rgb, alpha, bg):
    """Undo the mix with the white background on partly transparent pixels."""
    img = rgb.astype(np.float32)
    a = alpha[..., None]
    safe = np.maximum(a, 1e-3)
    fg = (img - (1 - a) * bg) / safe
    return np.where(a > 0.02, np.clip(fg, 0, 255), img)


def defringe(rgba, shave=0.6, bleed=2):
    """Shave the outer edge and pull edge colours from just inside the figure."""
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32) / 255
    # Shave: each pixel's alpha can't exceed its weakest neighbour by much.
    shrunk = ndi.minimum_filter(alpha, size=3)
    alpha = alpha * (1 - shave) + shrunk * shave
    alpha = np.clip((alpha - 0.12) / 0.88, 0, 1)
    # Colour bleed: the outer `bleed` pixels take the colour of the nearest solid pixel.
    solid = alpha >= 0.98
    inner = ndi.binary_erosion(solid, iterations=bleed)
    if inner.any():
        _, (iy, ix) = ndi.distance_transform_edt(~inner, return_indices=True)
        band = (alpha > 0) & ~inner
        src = rgb[iy, ix]
        # Only replace when the edge is lighter than the inside (that's the white leaking in).
        lighter = rgb.sum(axis=2) > src.sum(axis=2) + 12
        rgb = np.where((band & lighter)[..., None], src, rgb)
    rgb[alpha <= 0] = 0
    out = np.dstack([rgb, alpha * 255]).round().clip(0, 255).astype(np.uint8)
    return out


def strip_white_rims(rgba, reach=14):
    """Remove thin bits of leftover white along the outline, between hair strands.

    Works on a finished cutout, so it also cleans poses that no longer have a
    source sheet. Only near-neutral white next to dark strands goes; cream
    clothes, sneakers, paper and anything thicker than a few px stay.
    """
    rgb = rgba[..., :3].astype(np.int16)
    alpha = rgba[..., 3].copy()
    val = rgb.mean(axis=2)
    light = (rgb.min(axis=2) >= 215) & (rgb.max(axis=2) - rgb.min(axis=2) <= 16) & (alpha > 100)
    clear = alpha < 26
    near = ndi.distance_transform_edt(~clear)
    labels, n = ndi.label(light)
    drop = np.zeros(n + 1, bool)
    for i, sl in enumerate(ndi.find_objects(labels)):
        ys = slice(max(sl[0].start - 3, 0), sl[0].stop + 3)
        xs = slice(max(sl[1].start - 3, 0), sl[1].stop + 3)
        blob = labels[ys, xs] == i + 1
        if blob.sum() > 300 or near[ys, xs][blob].min() > reach:
            continue
        if ndi.distance_transform_edt(blob).max() > 5:
            continue
        ring = ndi.binary_dilation(blob, iterations=2) & ~blob & ~clear[ys, xs]
        if not ring.any():
            continue
        r, g, b = (rgb[ys, xs][ring][:, k] for k in range(3))
        skin = ((r > 170) & (r > g + 12) & (g > b) & (r - b < 140)).mean()
        # Hair strands all round it; eye whites also touch skin, so they stay.
        if (val[ys, xs][ring] < 110).mean() >= 0.55 and skin < 0.08:
            drop[i + 1] = True
    alpha[drop[labels]] = 0
    out = rgba.copy()
    out[..., 3] = alpha
    out[alpha == 0, :3] = 0
    return out


def keep_figure(alpha):
    """Keep the biggest blob and anything touching it; drop floating marks and specks."""
    solid = alpha > 0.35
    linked, n = ndi.label(ndi.binary_dilation(solid, iterations=1))
    if n == 0:
        return alpha
    sizes = ndi.sum(solid, linked, index=range(1, n + 1))
    main = linked == (int(np.argmax(sizes)) + 1)
    alpha = np.where(ndi.binary_dilation(main, iterations=1), alpha, 0)
    # Crumbs that only touch the figure by a pixel or two (shadow bits under wheels).
    bits, n = ndi.label(alpha > 0)
    if n > 1:
        sizes = np.asarray(ndi.sum(np.ones_like(alpha), bits, range(1, n + 1)))
        crumbs = np.zeros(n + 1, bool)
        crumbs[1:] = sizes < 80
        alpha = np.where(crumbs[bits], 0, alpha)
    return alpha


def extract(sheet_path, char_id):
    rgb = np.asarray(Image.open(sheet_path).convert('RGB'))
    alpha, bg = sheet_alpha(rgb)
    colour = unblend(rgb, alpha, bg)
    h, w = alpha.shape
    out_dir = os.path.join(root, char_id)
    os.makedirs(out_dir, exist_ok=True)

    # Assign each blob to the grid cell holding most of it, so art that pokes
    # over a cell line still goes with its own pose.
    blobs, n = ndi.label(ndi.binary_dilation(alpha > 0.35, iterations=2))
    ys, xs = np.mgrid[0:h, 0:w]
    cell_of_px = (np.minimum(ys * 3 // h, 2) * 3 + np.minimum(xs * 3 // w, 2))
    owner = np.full(n + 1, -1)
    for b in range(1, n + 1):
        cells = cell_of_px[blobs == b]
        owner[b] = np.bincount(cells, minlength=9).argmax()
    owner_map = owner[blobs]

    for i, pose in enumerate(POSES):
        mine = (owner_map == i) & (alpha > 0)
        a = keep_figure(np.where(mine, alpha, 0))
        rgba = np.dstack([colour, a * 255]).round().clip(0, 255).astype(np.uint8)
        rgba = strip_white_rims(rgba)
        rgba[..., 3] = (keep_figure(rgba[..., 3] / 255) * 255).round().astype(np.uint8)
        rgba = defringe(rgba)
        im = Image.fromarray(rgba, 'RGBA')
        bbox = im.getchannel('A').getbbox()
        im = im.crop(bbox)
        path = os.path.join(out_dir, f'{i + 1:02d}-{pose}.png')
        im.save(path, optimize=True)
        print(f'{os.path.relpath(path, root)}  {im.size}')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    extract(sys.argv[1], sys.argv[2])
