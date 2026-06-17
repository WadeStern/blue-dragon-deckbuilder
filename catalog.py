"""Scan the card-image folders into an in-memory catalog and serve cached
thumbnails / medium-size views."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

import config

# id -> {"id", "set", "filename", "path"}
_catalog = {}
_sets = []          # ordered list of set names that actually contain cards
_lock = threading.Lock()

# Background thumbnail pre-warming progress.
_warm = {"running": False, "done": 0, "total": 0, "phase": "idle"}
_warm_lock = threading.Lock()


def _nice_set_order(name):
    """Sort sets in a friendly reading order rather than raw alphabetical."""
    order = [
        "Light Starter",
        "Shadow Starter",
        "Demo Deck",
        "Set 1",
        "Set 2",
        "Parallel Shadows",
    ]
    return (order.index(name) if name in order else len(order), name)


def build():
    """(Re)scan CARDS_DIR. Safe to call again to pick up new files."""
    root = config.cards_dir()
    catalog = {}
    sets = set()
    collisions = []

    if os.path.isdir(root):
        for set_name in sorted(os.listdir(root)):
            set_path = os.path.join(root, set_name)
            if not os.path.isdir(set_path) or set_name in config.EXCLUDED_SETS:
                continue
            has_card = False
            for fname in sorted(os.listdir(set_path)):
                stem, ext = os.path.splitext(fname)
                if ext.lower() not in config.CARD_EXTS:
                    continue
                card_id = stem
                if card_id in catalog:
                    # Keep ids globally unique by prefixing the set on collision.
                    card_id = f"{set_name}__{stem}"
                    collisions.append(stem)
                catalog[card_id] = {
                    "id": card_id,
                    "set": set_name,
                    "filename": fname,
                    "path": os.path.join(set_path, fname),
                }
                has_card = True
            if has_card:
                sets.add(set_name)

    with _lock:
        _catalog.clear()
        _catalog.update(catalog)
        _sets[:] = sorted(sets, key=_nice_set_order)

    return {
        "root": root,
        "exists": os.path.isdir(root),
        "card_count": len(catalog),
        "sets": list(_sets),
        "collisions": collisions,
    }


def all_cards():
    """List of cards (id + set), ordered by set then id."""
    with _lock:
        cards = list(_catalog.values())
    cards.sort(key=lambda c: (_nice_set_order(c["set"]), c["id"]))
    return [{"id": c["id"], "set": c["set"]} for c in cards]


def sets():
    with _lock:
        return list(_sets)


def get(card_id):
    with _lock:
        return _catalog.get(card_id)


def exists(card_id):
    with _lock:
        return card_id in _catalog


# --------------------------------------------------------------------------- #
# Cached resized images
# --------------------------------------------------------------------------- #
def _cached_path(card_id, width, cache_dir):
    return os.path.join(cache_dir, f"{card_id}.jpg")


def cached_image(card_id, width, cache_dir):
    """Return a filesystem path to a width-px JPEG of the card, generating and
    caching it on first request. Returns None if the card is unknown."""
    card = get(card_id)
    if card is None or not os.path.isfile(card["path"]):
        return None

    out = _cached_path(card_id, width, cache_dir)
    src_mtime = os.path.getmtime(card["path"])
    if os.path.isfile(out) and os.path.getmtime(out) >= src_mtime:
        return out

    with Image.open(card["path"]) as im:
        im = im.convert("RGB")
        if im.width > width:
            height = round(im.height * width / im.width)
            im = im.resize((width, height), Image.LANCZOS)
        im.save(out, "JPEG", quality=82, optimize=True)
    return out


def thumb_path(card_id):
    return cached_image(card_id, config.THUMB_WIDTH, config.THUMB_DIR)


def view_path(card_id):
    return cached_image(card_id, config.VIEW_WIDTH, config.VIEW_DIR)


def source_path(card_id):
    card = get(card_id)
    return card["path"] if card else None


# --------------------------------------------------------------------------- #
# Background cache pre-warming
# --------------------------------------------------------------------------- #
def warm_state():
    with _warm_lock:
        return dict(_warm)


def _warm_bump(phase=None):
    with _warm_lock:
        _warm["done"] += 1
        if phase:
            _warm["phase"] = phase


def warm_cache(warm_views=False, workers=None):
    """Pre-generate every thumbnail (and optionally the medium view cache) so
    browsing is instant. Skips files already cached. Safe to run in a thread."""
    workers = workers or min(8, (os.cpu_count() or 4))
    with _lock:
        ids = list(_catalog.keys())

    jobs = [("thumb", cid) for cid in ids]
    if warm_views:
        jobs += [("view", cid) for cid in ids]

    with _warm_lock:
        _warm.update(running=True, done=0, total=len(jobs), phase="thumbnails")

    def job(item):
        kind, cid = item
        try:
            thumb_path(cid) if kind == "thumb" else view_path(cid)
        except Exception:
            pass
        _warm_bump(phase="views" if kind == "view" else None)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(job, jobs))

    with _warm_lock:
        _warm.update(running=False, phase="done")


def warm_cache_async(warm_views=False):
    t = threading.Thread(target=warm_cache, kwargs={"warm_views": warm_views},
                         daemon=True)
    t.start()
    return t
