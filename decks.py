"""Decklist persistence: one JSON file per deck under decks/."""
import json
import os
import re
import time

import catalog
import config


def _slug(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "deck"


def _path(deck_id):
    return os.path.join(config.DECKS_DIR, f"{deck_id}.json")


def _unique_id(base):
    deck_id = base
    n = 2
    while os.path.exists(_path(deck_id)):
        deck_id = f"{base}-{n}"
        n += 1
    return deck_id


def list_decks():
    out = []
    for fname in os.listdir(config.DECKS_DIR):
        if not fname.endswith(".json"):
            continue
        deck = _read(fname[:-5])
        if deck is None:
            continue
        cards = deck.get("cards", {})
        out.append({
            "id": deck["id"],
            "name": deck.get("name", deck["id"]),
            "total": sum(cards.values()),
            "unique": len(cards),
            "modified": deck.get("modified", 0),
            "sample": list(cards.keys())[:5],
        })
    out.sort(key=lambda d: d.get("modified", 0), reverse=True)
    return out


def _read(deck_id):
    path = _path(deck_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    data.setdefault("id", deck_id)
    data.setdefault("name", deck_id)
    data.setdefault("cards", {})
    return data


def get(deck_id):
    return _read(deck_id)


def get_resolved(deck_id):
    """Deck plus per-card label info, dropping any cards no longer in the catalog."""
    deck = _read(deck_id)
    if deck is None:
        return None
    items = []
    missing = []
    for cid, cnt in deck["cards"].items():
        rec = catalog.get(cid)
        if rec is None:
            missing.append(cid)
            continue
        label = rec["label"]
        items.append({
            "id": cid,
            "set": label.set if label else None,
            "name": label.name if label else None,
            "count": cnt,
        })
    items.sort(key=lambda i: (i["set"] or "~", (i["name"] or "").lower(), i["id"]))
    return {
        "id": deck["id"],
        "name": deck["name"],
        "cards": items,
        "total": sum(i["count"] for i in items),
        "missing": missing,
    }


def _write(deck):
    deck["modified"] = int(time.time())
    with open(_path(deck["id"]), "w", encoding="utf-8") as fh:
        json.dump(deck, fh, indent=2)
    return deck


def create(name):
    deck_id = _unique_id(_slug(name))
    deck = {"id": deck_id, "name": name.strip() or "Untitled Deck",
            "cards": {}, "created": int(time.time())}
    return _write(deck)


def _group_cap_for(deck_cards, target_id):
    """Return the maximum number of `target_id` allowed given the existing
    deck contents. The 3-card limit is shared across cards in the same
    canonical duplicate group, so adding more of target_id is constrained
    by what's already in the deck from its group."""
    target_canonical = catalog.resolve_canonical(target_id)
    used_in_group = 0
    for cid, cnt in deck_cards.items():
        if cid == target_id:
            continue
        if catalog.resolve_canonical(cid) == target_canonical:
            used_in_group += cnt
    return max(0, config.MAX_COPIES_PER_CARD - used_in_group)


def update(deck_id, name=None, cards=None):
    deck = _read(deck_id)
    if deck is None:
        return None
    if name is not None:
        deck["name"] = name.strip() or deck["name"]
    if cards is not None:
        # Aggregate counts per canonical, then re-distribute. This both
        # caps each individual id at MAX and caps each group at MAX too.
        group_totals = {}
        ordered = []
        for cid, cnt in cards.items():
            cnt = int(cnt)
            if cnt <= 0 or not catalog.exists(cid):
                continue
            canonical = catalog.resolve_canonical(cid)
            group_totals.setdefault(canonical, 0)
            ordered.append((cid, cnt, canonical))
        clean = {}
        used = {canonical: 0 for canonical in group_totals}
        for cid, cnt, canonical in ordered:
            allowed = config.MAX_COPIES_PER_CARD - used[canonical]
            take = max(0, min(cnt, allowed, config.MAX_COPIES_PER_CARD))
            if take > 0:
                clean[cid] = take
                used[canonical] += take
        deck["cards"] = clean
    return _write(deck)


def set_card(deck_id, card_id, count):
    """Set the count for a single card (0 removes it). Returns updated deck."""
    deck = _read(deck_id)
    if deck is None or not catalog.exists(card_id):
        return None
    count = int(count)
    if count <= 0:
        deck["cards"].pop(card_id, None)
    else:
        cap = min(config.MAX_COPIES_PER_CARD,
                  _group_cap_for(deck["cards"], card_id))
        deck["cards"][card_id] = max(0, min(count, cap))
        if deck["cards"][card_id] == 0:
            deck["cards"].pop(card_id, None)
    return _write(deck)


def delete(deck_id):
    path = _path(deck_id)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
