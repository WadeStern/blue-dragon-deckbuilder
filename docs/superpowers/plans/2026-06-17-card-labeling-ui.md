# In-UI card labeling editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Click a card → see it enlarged in a modal with a form alongside → autosaves to `labels.csv` → ◀/▶ walks the current filtered view. Type / element / set vocabularies are server-defined and returned via a new `/api/vocab` endpoint.

**Architecture:** A new `vocab.py` owns the seeded constants. `labels.py` learns to parse and serialize the pipe-separated `element` cell and to emit lenient warnings. `catalog.py` keeps the labels `rows` dict alive after `build()`, gets a module-level `threading.Lock`, and exposes `save_label()`. Two new Flask routes (`GET /api/vocab`, `PUT /api/labels/<id>`) wire the front-end. A new `static/editor.js` replaces the old click-to-zoom modal with the full editor.

**Tech Stack:** Python 3.10+, Flask 3, vanilla JS, CSV via stdlib, pytest.

**Reference spec:** `docs/superpowers/specs/2026-06-17-card-labeling-ui-design.md`

**Sequencing note:** Element changes from scalar to list across the API. Task 2 flips this in one atomic commit (backend + frontend filter pipeline) so the browser is never broken between commits.

---

## Task 1: labels.py — multi-element parse, lenient warnings, dump

**Files:**
- Create: `vocab.py`
- Modify: `labels.py`
- Modify: `tests/test_labels.py`

`LabelRow.element` switches from `str` to `tuple[str, ...]` (frozen-dataclass-friendly). Parse pipe-separated values, lowercase + sort + dedupe. Lenient warnings cover unknown element / type values and Command/Skill rows that carry element data. New `dump(rows, path)` performs an atomic CSV rewrite.

- [ ] **Step 1: Create vocab.py with the seeded constants**

```python
"""Locked vocabularies for card type, element/attribute, and the seeded set
list. Sets are extensible — the editor merges these with anything found in
labels.csv (see catalog.sets_seen)."""

KNOWN_TYPES = ("Shadows", "Partners", "Skills", "Commands")

KNOWN_ELEMENTS = ("light", "dark", "fire", "water", "earth", "wind", "none")

# Types that CANNOT carry an element. The editor hides the element block for
# these; the API forces element=[] on save; the loader warns if it sees one.
TYPES_WITHOUT_ELEMENT = frozenset({"Commands", "Skills"})

SEEDED_SETS = (
    "Light Starter",
    "Shadow Starter",
    "Demo Deck",
    "Set 1",
    "Set 2",
    "Parallel Shadows",
)
```

- [ ] **Step 2: Write failing tests for the new labels behavior**

Append to `tests/test_labels.py`:

```python
def test_element_parses_pipe_separated(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDX1-EN_0001,Set 1,Twoface,light|dark,Shadows
    """)
    rows, _ = labels.load(str(p))
    row = rows["BDX1-EN_0001"]
    # Sorted, lowercased, tuple of strings.
    assert row.element == ("dark", "light")


def test_element_lowercased_and_sorted(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDX1-EN_0001,Set 1,X,Wind|Fire|EARTH,Shadows
    """)
    rows, _ = labels.load(str(p))
    assert rows["BDX1-EN_0001"].element == ("earth", "fire", "wind")


def test_single_element_becomes_singleton_tuple(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDS1-EN_0001,Light Starter,Phoenix,light,Shadows
    """)
    rows, _ = labels.load(str(p))
    assert rows["BDS1-EN_0001"].element == ("light",)


def test_empty_element_is_empty_tuple(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDC1-EN_0001,Set 1,Bolt,,Commands
    """)
    rows, _ = labels.load(str(p))
    assert rows["BDC1-EN_0001"].element == ()


def test_unknown_element_warns(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDX1-EN_0001,Set 1,X,purple,Shadows
    """)
    rows, warnings = labels.load(str(p))
    assert rows["BDX1-EN_0001"].element == ("purple",)
    assert any("purple" in w and "element" in w.lower() for w in warnings)


def test_unknown_type_warns(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDX1-EN_0001,Set 1,X,light,Vehicles
    """)
    rows, warnings = labels.load(str(p))
    assert rows["BDX1-EN_0001"].type == "Vehicles"
    assert any("Vehicles" in w and "type" in w.lower() for w in warnings)


def test_command_with_element_warns(tmp_path):
    p = write_csv(tmp_path, """
        id,set,name,element,type
        BDC1-EN_0001,Set 1,Bolt,fire,Commands
    """)
    rows, warnings = labels.load(str(p))
    # Loaded as-is; the API layer will drop the element. Warning surfaces here.
    assert rows["BDC1-EN_0001"].element == ("fire",)
    assert any("Commands" in w and "element" in w.lower() for w in warnings)


def test_dump_roundtrip(tmp_path):
    src_path = write_csv(tmp_path, """
        id,set,name,element,type
        BDB-EN_0002,Set 1,Beta,light|dark,Shadows
        BDA-EN_0001,Set 1,Alpha,fire,Partners
    """)
    rows, _ = labels.load(str(src_path))

    out = tmp_path / "out.csv"
    labels.dump(rows, str(out))

    # File is sorted by id.
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "id,set,name,element,type"
    assert lines[1].startswith("BDA-EN_0001,")
    assert lines[2].startswith("BDB-EN_0002,")
    # Multi-element joined with |, alphabetical.
    assert "dark|light" in lines[2]

    # Round-trip: loading the output yields identical rows.
    rows2, _ = labels.load(str(out))
    assert rows2 == rows


def test_dump_is_atomic(tmp_path, monkeypatch):
    """If os.replace fails the original file must be intact."""
    out = tmp_path / "labels.csv"
    out.write_text("id,set,name,element,type\noriginal,Set,O,light,Shadows\n",
                   encoding="utf-8")
    original_bytes = out.read_bytes()

    def boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr("os.replace", boom)

    rows_to_write = {"X": labels.LabelRow("X", "Set", "X", ("light",), "Shadows")}
    with pytest.raises(OSError):
        labels.dump(rows_to_write, str(out))

    assert out.read_bytes() == original_bytes
```

Also update the existing `test_load_basic` and similar tests to expect `element` as a tuple. Replace inside `tests/test_labels.py`:

```python
# In test_load_basic, change:
    assert jiro.element == "earth"
# To:
    assert jiro.element == ("earth",)

# In test_load_trims_whitespace, change:
    assert row.element == "light"
# To:
    assert row.element == ("light",)

# test_blank_cells_allowed_and_warned: change
    assert row.element == ""
# To:
    assert row.element == ()
```

Note: this test also asserts a "blank" warning; the new loader still emits one for `element=()` when the row exists (preserves the existing test's intent).

- [ ] **Step 3: Run the tests and verify they all fail**

Run: `.venv/bin/pytest tests/test_labels.py -v 2>&1 | tail -25`
Expected: the new tests fail and the existing ones that compare element to a string also fail.

- [ ] **Step 4: Update labels.py**

Replace `labels.py` entirely:

```python
"""Parse the labels.csv metadata file into in-memory rows.

Returned by load():
  rows:     dict[id, LabelRow]  -- whitespace-trimmed, raw-case fields
  warnings: list[str]           -- non-fatal issues (missing file, blank
                                   cells, unknown vocab, ...)

Raises LabelError on structural problems (duplicate id, missing required
column, malformed CSV)."""
import csv
import os
from dataclasses import dataclass

import vocab


REQUIRED_COLUMNS = ("id", "set", "name", "element", "type")


class LabelError(ValueError):
    """Structural problem with labels.csv that prevents the app from running."""


@dataclass(frozen=True)
class LabelRow:
    id: str
    set: str
    name: str
    element: tuple    # sorted, lowercased, deduped
    type: str


def _parse_elements(cell):
    """`light|Dark` -> ('dark', 'light'). Empty / blank -> ()."""
    parts = [p.strip().lower() for p in cell.split("|")]
    return tuple(sorted({p for p in parts if p}))


def load(path):
    if not os.path.isfile(path):
        return {}, [f"labels.csv not found at {os.path.abspath(path)}"]

    rows = {}
    warnings = []

    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            raise LabelError(f"{path}: file is empty (expected header row)")

        header = [h.strip() for h in header]
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise LabelError(
                f"{path}: missing required column(s): {', '.join(missing)}"
            )
        idx = {c: header.index(c) for c in REQUIRED_COLUMNS}

        for line_no, raw in enumerate(reader, start=2):
            if not raw or all(not (c or "").strip() for c in raw):
                continue
            cells = [(raw[i].strip() if i < len(raw) else "")
                     for i in range(len(header))]
            row_id = cells[idx["id"]]
            if not row_id:
                warnings.append(f"{path}:{line_no} blank id, row skipped")
                continue
            if row_id in rows:
                raise LabelError(
                    f"{path}:{line_no} duplicate id {row_id!r}"
                )

            row = LabelRow(
                id=row_id,
                set=cells[idx["set"]],
                name=cells[idx["name"]],
                element=_parse_elements(cells[idx["element"]]),
                type=cells[idx["type"]],
            )

            blanks = [f for f in ("name", "type") if not getattr(row, f)]
            if not row.element and row.type not in vocab.TYPES_WITHOUT_ELEMENT:
                blanks.append("element")
            if blanks:
                warnings.append(
                    f"{path}:{line_no} {row.id} has blank {', '.join(blanks)}"
                )

            for el in row.element:
                if el not in vocab.KNOWN_ELEMENTS:
                    warnings.append(
                        f"{path}:{line_no} {row.id} has unknown element {el!r}"
                    )
            if row.type and row.type not in vocab.KNOWN_TYPES:
                warnings.append(
                    f"{path}:{line_no} {row.id} has unknown type {row.type!r}"
                )
            if row.type in vocab.TYPES_WITHOUT_ELEMENT and row.element:
                warnings.append(
                    f"{path}:{line_no} {row.id} type={row.type} carries element "
                    f"{list(row.element)!r}; element will be ignored over the API"
                )

            rows[row_id] = row

    return rows, warnings


def dump(rows, path):
    """Atomically rewrite `path` with the rows sorted by id."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, lineterminator="\n")
            writer.writerow(REQUIRED_COLUMNS)
            for cid in sorted(rows):
                row = rows[cid]
                writer.writerow([
                    row.id,
                    row.set,
                    row.name,
                    "|".join(row.element),
                    row.type,
                ])
        os.replace(tmp, path)
    except Exception:
        # Clean up the half-written tmp on any failure so we don't leak it.
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
```

- [ ] **Step 5: Run the tests and verify they pass**

Run: `.venv/bin/pytest tests/test_labels.py -v 2>&1 | tail -25`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add vocab.py labels.py tests/test_labels.py
git -c commit.gpgsign=false commit -m "labels: vocab module, multi-element parse, lenient warnings, dump"
```

---

## Task 2: Element list-flip (catalog API shape + filter pipeline)

**Files:**
- Modify: `catalog.py`
- Modify: `static/filters.js`
- Modify: `tests/test_catalog.py`

`/api/cards` per-card `element` flips from `string|null` to `string[]`. `cardPasses` and `elements_seen` are updated together so the browser is never broken between commits.

- [ ] **Step 1: Update catalog tests for the list shape**

In `tests/test_catalog.py`:

Update the fixture rows (both labeled cards stay single-element for now, plus add a multi-element card to prove the flatten works):

```python
    labels_csv.write_text(
        "id,set,name,element,type\n"
        "BDS1-EN_0001,Light Starter,Phoenix,Light,Shadows\n"
        "BDS1-EN_0002,Light Starter,Jiro,light,Partners\n"
        "BDS1-EN_8888,Light Starter,Ghost,light,Shadows\n",   # orphan
        encoding="utf-8",
    )
```

Update `test_seen_values_dedupe_case_insensitive` so the list-flatten is exercised:

```python
def test_seen_values_dedupe_case_insensitive(fake_cards):
    catalog = fake_cards
    catalog.build()
    elements = catalog.elements_seen()
    # Both cards use light (case-insensitive); dedupe to one chip.
    assert elements == ["light"]

    types = catalog.types_seen()
    assert sorted(types) == ["Partners", "Shadows"]
```

Add a new test verifying the API shape:

```python
def test_api_card_returns_element_list(fake_cards):
    catalog = fake_cards
    catalog.build()
    api_cards = catalog.all_cards()
    by_id = {c["id"]: c for c in api_cards}

    # Labeled card: element is a non-empty list of strings.
    assert by_id["BDS1-EN_0001"]["element"] == ["light"]
    # Unlabeled card: element is an empty list (not None).
    assert by_id["BDS1-EN_9999"]["element"] == []
```

- [ ] **Step 2: Run catalog tests — verify they fail**

Run: `.venv/bin/pytest tests/test_catalog.py -v 2>&1 | tail -10`
Expected: failures (`element` is currently None or a scalar).

- [ ] **Step 3: Update catalog.py**

In `catalog.py`, change two spots.

`_record_to_api`:

```python
def _record_to_api(rec):
    """Public record shape returned over the wire."""
    label = rec["label"]
    if label is None:
        return {"id": rec["id"], "set": None, "name": None,
                "element": [], "type": None}
    return {
        "id": rec["id"],
        "set": label.set,
        "name": label.name,
        "element": list(label.element),   # tuple -> list for JSON
        "type": label.type,
    }
```

`build()` — the line that produces `elements_list` needs to flatten across each row's tuple:

Change:

```python
    elements_list = _first_seen_display(rec["label"].element for rec in labeled)
```

To:

```python
    elements_list = _first_seen_display(
        el for rec in labeled for el in rec["label"].element
    )
```

`all_cards()` — the sort key references `label.name.lower()`, which still works since `name` is still a string. Element isn't part of the sort key.

- [ ] **Step 4: Update filters.js for the list-valued element**

In `static/filters.js`, replace `cardPasses`:

```javascript
function cardPasses(card, state) {
  if (state.hideUnlabeled && !card.name && !card.set) return false;

  if (state.selectedSets.size && !state.selectedSets.has((card.set || "").toLowerCase())) return false;

  if (state.selectedElements.size) {
    const els = (card.element || []).map(e => e.toLowerCase());
    let any = false;
    for (const sel of state.selectedElements) {
      if (els.includes(sel)) { any = true; break; }
    }
    if (!any) return false;
  }

  if (state.selectedTypes.size
      && !state.selectedTypes.has((card.type || "").toLowerCase())) return false;

  const q = (state.search || "").trim().toLowerCase();
  if (q) {
    const hay = `${card.id} ${card.name || ""}`.toLowerCase();
    if (!hay.includes(q)) return false;
  }
  return true;
}
```

- [ ] **Step 5: Run all tests + functional filter check**

```bash
.venv/bin/pytest -q 2>&1 | tail -3
echo "--- filters.js list-element behavior ---"
node -e "
$(cat static/filters.js)
const cards = [
  { id: 'BDX1-EN_0042', set: 'Set 1', name: 'Twoface', element: ['light','dark'], type: 'Shadows' },
  { id: 'BDS1-EN_0001', set: 'Light Starter', name: 'Phoenix', element: ['light'], type: 'Shadows' },
  { id: 'BDC1-EN_0001', set: 'Set 1', name: 'Bolt', element: [], type: 'Commands' },
];
let s = { selectedSets:new Set(), selectedElements:new Set(['dark']), selectedTypes:new Set(), search:'', hideUnlabeled:false };
console.log('element=dark:', cards.filter(c=>cardPasses(c,s)).length, '(expect 1, Twoface)');
s.selectedElements = new Set(['light']);
console.log('element=light:', cards.filter(c=>cardPasses(c,s)).length, '(expect 2: Twoface + Phoenix)');
s.selectedElements = new Set();
s.selectedTypes = new Set(['commands']);
console.log('type=commands:', cards.filter(c=>cardPasses(c,s)).length, '(expect 1, Bolt)');
"
```

Expected: all pytest tests pass; the three printed lines each match the expected count.

- [ ] **Step 6: Commit**

```bash
git add catalog.py static/filters.js tests/test_catalog.py
git -c commit.gpgsign=false commit -m "Element is a list across the API and the filter pipeline"
```

---

## Task 3: catalog.save_label — write path + module lock

**Files:**
- Modify: `catalog.py`
- Create: `tests/test_labels_save.py`

Add the module-level `threading.Lock`, keep the labels `rows` dict alive after `build()`, and add `save_label()`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_labels_save.py`:

```python
import importlib
import os
import threading

import pytest


@pytest.fixture
def fake_world(tmp_path, monkeypatch):
    """A cards dir + empty labels.csv, with config/catalog reloaded to point
    at them. Returns the catalog module."""
    cards = tmp_path / "cards"
    cards.mkdir()
    for fname in ("BDS1-EN_0001.jpg", "BDS1-EN_0002.jpg", "BDC1-EN_0001.jpg"):
        (cards / fname).write_bytes(b"x")

    labels_csv = tmp_path / "labels.csv"
    labels_csv.write_text("id,set,name,element,type\n", encoding="utf-8")

    monkeypatch.setenv("BD_CARDS_DIR", str(cards))
    monkeypatch.setenv("BD_LABELS_PATH", str(labels_csv))

    import config
    import catalog
    importlib.reload(config)
    importlib.reload(catalog)
    catalog.build()
    return catalog, labels_csv


def test_save_creates_row(fake_world):
    catalog, csv_path = fake_world
    rec = catalog.save_label("BDS1-EN_0001", {
        "name": "Phoenix",
        "set": "Light Starter",
        "type": "Shadows",
        "element": ["light"],
    })
    assert rec["name"] == "Phoenix"
    assert rec["element"] == ["light"]

    # Persisted.
    text = csv_path.read_text(encoding="utf-8")
    assert "Phoenix" in text
    assert "BDS1-EN_0001,Light Starter,Phoenix,light,Shadows" in text


def test_save_updates_existing_row(fake_world):
    catalog, _ = fake_world
    catalog.save_label("BDS1-EN_0001", {
        "name": "Phoenix",
        "set": "Light Starter",
        "type": "Shadows",
        "element": ["light"],
    })
    rec = catalog.save_label("BDS1-EN_0001", {
        "name": "Phoenix Reborn",
        "set": "Light Starter",
        "type": "Shadows",
        "element": ["light", "fire"],
    })
    assert rec["name"] == "Phoenix Reborn"
    assert rec["element"] == ["fire", "light"]   # sorted


def test_save_unknown_card_raises(fake_world):
    catalog, _ = fake_world
    with pytest.raises(KeyError):
        catalog.save_label("NOPE-EN_9999", {
            "name": "Ghost",
            "set": "Set 1",
            "type": "Shadows",
            "element": ["light"],
        })


def test_save_command_clears_element(fake_world):
    catalog, csv_path = fake_world
    rec = catalog.save_label("BDC1-EN_0001", {
        "name": "Bolt",
        "set": "Set 1",
        "type": "Commands",
        "element": ["fire", "light"],   # client lied; server must clear
    })
    assert rec["element"] == []
    text = csv_path.read_text(encoding="utf-8")
    assert "BDC1-EN_0001,Set 1,Bolt,,Commands" in text


def test_concurrent_saves_dont_corrupt(fake_world):
    catalog, csv_path = fake_world
    ready = threading.Barrier(2)
    errors = []

    def worker(cid, name):
        ready.wait()
        try:
            catalog.save_label(cid, {
                "name": name, "set": "Light Starter",
                "type": "Shadows", "element": ["light"],
            })
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker, args=("BDS1-EN_0001", "Alpha"))
    t2 = threading.Thread(target=worker, args=("BDS1-EN_0002", "Beta"))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert errors == []

    # Both rows landed.
    text = csv_path.read_text(encoding="utf-8")
    assert "BDS1-EN_0001,Light Starter,Alpha,light,Shadows" in text
    assert "BDS1-EN_0002,Light Starter,Beta,light,Shadows" in text


def test_in_memory_catalog_updates(fake_world):
    catalog, _ = fake_world
    catalog.save_label("BDS1-EN_0001", {
        "name": "Phoenix",
        "set": "Light Starter",
        "type": "Shadows",
        "element": ["light"],
    })
    rec = catalog.get_api("BDS1-EN_0001")
    assert rec["name"] == "Phoenix"
    assert rec["element"] == ["light"]
```

- [ ] **Step 2: Run the tests — verify they fail**

Run: `.venv/bin/pytest tests/test_labels_save.py -v 2>&1 | tail -15`
Expected: `AttributeError: module 'catalog' has no attribute 'save_label'`.

- [ ] **Step 3: Update catalog.py with save_label**

Top of `catalog.py`, change the imports / state block. Replace:

```python
# id -> {"id", "filename", "path", "label": LabelRow | None}
_catalog = {}
_sets = []
_elements = []
_types = []
_lock = threading.Lock()
```

with:

```python
import vocab

# id -> {"id", "filename", "path", "label": LabelRow | None}
_catalog = {}
_label_rows = {}        # id -> LabelRow ; the live in-memory copy of labels.csv
_sets = []
_elements = []
_types = []
_lock = threading.Lock()
```

In `build()`, after computing `rows, label_warnings = labels.load(...)` and before the `with _lock:` block, store the rows for later writes:

Replace:

```python
    with _lock:
        _catalog.clear()
        _catalog.update(catalog)
        _sets[:] = sets_list
        _elements[:] = elements_list
        _types[:] = types_list
```

with:

```python
    with _lock:
        _catalog.clear()
        _catalog.update(catalog)
        _label_rows.clear()
        _label_rows.update(rows)
        _sets[:] = sets_list
        _elements[:] = elements_list
        _types[:] = types_list
```

Add the `save_label` function (place it near `get` / `exists`):

```python
def save_label(card_id, payload):
    """Persist a label edit. Mutates labels.csv atomically and updates the
    in-memory catalog so the next /api/cards call sees the change without a
    full rescan.

    payload = {"name": str, "set": str, "type": str, "element": list[str]}

    Raises KeyError if `card_id` is not in the image scan.
    Returns the updated public API record for the card.
    """
    name = (payload.get("name") or "").strip()
    set_name = (payload.get("set") or "").strip()
    type_ = (payload.get("type") or "").strip()
    raw_elements = payload.get("element") or []

    # Type-element coupling: Commands and Skills carry no element.
    if type_ in vocab.TYPES_WITHOUT_ELEMENT:
        element = ()
    else:
        element = tuple(sorted({
            e.strip().lower() for e in raw_elements if e and e.strip()
        }))

    with _lock:
        if card_id not in _catalog:
            raise KeyError(card_id)

        row = labels.LabelRow(
            id=card_id, set=set_name, name=name,
            element=element, type=type_,
        )
        _label_rows[card_id] = row
        labels.dump(_label_rows, config.labels_path())

        _catalog[card_id]["label"] = row

        # A newly-seen set name flows into the chip list immediately.
        if set_name and set_name not in _sets:
            _sets.append(set_name)

        return _record_to_api(_catalog[card_id])
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -5`
Expected: all pass (the new test_labels_save tests + existing tests).

- [ ] **Step 5: Commit**

```bash
git add catalog.py tests/test_labels_save.py
git -c commit.gpgsign=false commit -m "catalog.save_label: atomic labels.csv write + in-memory update"
```

---

## Task 4: app.py — /api/vocab and /api/labels/<card_id>

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add the two routes**

After the existing `/api/cards` route in `app.py`, insert:

```python
@app.route("/api/vocab")
def api_vocab():
    """Vocabularies used by the editor (and, in a follow-up task, the chip
    filters). Sets are the union of seeded defaults and anything seen in
    labels.csv."""
    seeded = list(vocab.SEEDED_SETS)
    seen = catalog.sets_seen()
    merged = list(seeded) + [s for s in seen if s not in seeded]
    return jsonify({
        "types": list(vocab.KNOWN_TYPES),
        "elements": list(vocab.KNOWN_ELEMENTS),
        "sets": merged,
    })


@app.route("/api/labels/<card_id>", methods=["PUT"])
def api_label_put(card_id):
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("element"), list):
        abort(400)
    if not isinstance(body.get("name", ""), str): abort(400)
    if not isinstance(body.get("set", ""), str): abort(400)
    if not isinstance(body.get("type", ""), str): abort(400)
    try:
        rec = catalog.save_label(card_id, body)
    except KeyError:
        abort(404)
    return jsonify(rec)
```

And at the top of `app.py`, add `import vocab` alongside the existing imports.

- [ ] **Step 2: Boot the server and curl-smoke the new routes**

```bash
pkill -9 -f "app.py" 2>/dev/null; sleep 1
.venv/bin/python app.py > /tmp/bd-app.log 2>&1 &
disown
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ | grep -q 200; do sleep 1; done

echo "--- /api/vocab ---"
curl -s http://127.0.0.1:5000/api/vocab | python3 -m json.tool

echo "--- PUT /api/labels/BDS1-EN_0001 ---"
curl -s -X PUT http://127.0.0.1:5000/api/labels/BDS1-EN_0001 \
  -H 'Content-Type: application/json' \
  -d '{"name":"Phoenix","set":"Light Starter","type":"Shadows","element":["light"]}' \
  | python3 -m json.tool

echo "--- /api/cards picks up the change ---"
curl -s http://127.0.0.1:5000/api/cards \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print([c for c in d['cards'] if c['id']=='BDS1-EN_0001'][0])"

echo "--- 404 on unknown id ---"
curl -s -o /dev/null -w "code=%{http_code}\n" -X PUT \
  http://127.0.0.1:5000/api/labels/NOPE-EN_9999 \
  -H 'Content-Type: application/json' \
  -d '{"name":"X","set":"S","type":"Shadows","element":[]}'

echo "--- 400 on missing element key ---"
curl -s -o /dev/null -w "code=%{http_code}\n" -X PUT \
  http://127.0.0.1:5000/api/labels/BDS1-EN_0001 \
  -H 'Content-Type: application/json' \
  -d '{"name":"X","set":"S","type":"Shadows"}'

pkill -9 -f "app.py" 2>/dev/null; sleep 1
```

Expected:
- `/api/vocab` returns the four types, seven elements, and six seeded sets.
- The PUT returns the updated card record with `element: ["light"]`.
- `/api/cards` shows BDS1-EN_0001 with name=Phoenix, element=["light"].
- 404 on unknown id.
- 400 on missing element key.

- [ ] **Step 3: Revert the smoke-test edit so the labels.csv stays clean**

We just wrote a row to `labels.csv` during the smoke test. Revert it:

```bash
git diff --stat labels.csv && git checkout labels.csv
cat labels.csv
```

Expected: `labels.csv` is back to the single header row.

- [ ] **Step 4: Run pytest**

Run: `.venv/bin/pytest -q 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app.py
git -c commit.gpgsign=false commit -m "Add GET /api/vocab and PUT /api/labels/<card_id>"
```

---

## Task 5: static/editor.js — the modal editor

**Files:**
- Create: `static/editor.js`
- Modify: `static/style.css` (append editor styles)

`editor.js` exports `openEditor(cards, index, opts)`. `cards` is the filtered list the page is currently showing; `index` is the clicked card's position; `opts.onSave(card)` is called with the updated card after each successful save.

- [ ] **Step 1: Create static/editor.js**

```javascript
// Card editor modal. Replaces the old image-only zoom.
//
// openEditor(cards, index, { onSave, getVocab }):
//   cards         array of card records (id, set, name, element[], type)
//   index         starting index into `cards`
//   opts.onSave   called with the updated card record after each save
//   opts.getVocab returns a Promise that resolves to {types, elements, sets}

let _modal = null;
let _state = null;

function _build() {
  const modal = document.createElement("div");
  modal.className = "editor-modal";
  modal.innerHTML = `
    <div class="editor-stage">
      <button class="ed-nav prev" aria-label="previous">◀</button>
      <div class="editor-body">
        <div class="editor-image"><img alt=""></div>
        <div class="editor-form">
          <div class="ed-head">
            <span class="ed-id"></span>
            <span class="ed-pos"></span>
          </div>
          <label>Name <input type="text" class="ed-name" autocomplete="off"></label>
          <label>Set
            <select class="ed-set"></select>
          </label>
          <label>Type
            <select class="ed-type"></select>
          </label>
          <div class="ed-element-block">
            <div class="ed-element-label">Element</div>
            <div class="ed-element-chips"></div>
          </div>
          <div class="ed-status"></div>
        </div>
      </div>
      <button class="ed-nav next" aria-label="next">▶</button>
    </div>`;
  document.body.appendChild(modal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) close();
  });
  modal.querySelector(".prev").addEventListener("click", () => move(-1));
  modal.querySelector(".next").addEventListener("click", () => move(+1));
  modal.querySelector(".ed-name").addEventListener("input", scheduleSave);
  modal.querySelector(".ed-set").addEventListener("change", onSetChange);
  modal.querySelector(".ed-type").addEventListener("change", onTypeChange);
  return modal;
}

function _ensure() {
  if (!_modal) _modal = _build();
  return _modal;
}

function close() {
  if (_modal) _modal.classList.remove("open");
  _state = null;
  document.removeEventListener("keydown", _onKey);
}

function _onKey(e) {
  if (!_state) return;
  if (e.key === "Escape") { close(); }
  else if (e.key === "ArrowLeft") { move(-1); }
  else if (e.key === "ArrowRight") { move(+1); }
}

function setStatus(text, kind) {
  const el = _modal.querySelector(".ed-status");
  el.textContent = text;
  el.dataset.kind = kind || "";
}

function move(delta) {
  flushSave();
  const next = _state.index + delta;
  if (next < 0 || next >= _state.cards.length) return;
  _state.index = next;
  loadCurrent();
}

function loadCurrent() {
  const card = _state.cards[_state.index];
  const m = _modal;
  m.querySelector(".ed-id").textContent = card.id;
  m.querySelector(".ed-pos").textContent = `${_state.index + 1} / ${_state.cards.length}`;
  m.querySelector(".editor-image img").src =
    `/api/card/${encodeURIComponent(card.id)}/view`;

  m.querySelector(".ed-name").value = card.name || "";

  populateSet(card.set || "");
  populateType(card.type || "");
  populateElement(card.element || []);
  toggleElementBlock(card.type);

  m.querySelector(".prev").disabled = _state.index === 0;
  m.querySelector(".next").disabled = _state.index === _state.cards.length - 1;
  setStatus("", "");
}

function populateSet(currentSet) {
  const sel = _modal.querySelector(".ed-set");
  sel.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = ""; blank.textContent = "—";
  sel.appendChild(blank);
  for (const s of _state.vocab.sets) {
    const o = document.createElement("option"); o.value = s; o.textContent = s;
    sel.appendChild(o);
  }
  // Custom (user-added) sets not in vocab.sets yet
  if (currentSet && !_state.vocab.sets.includes(currentSet)) {
    const o = document.createElement("option");
    o.value = currentSet; o.textContent = currentSet;
    sel.appendChild(o);
  }
  const add = document.createElement("option");
  add.value = "__add__"; add.textContent = "+ Add new set…";
  sel.appendChild(add);
  sel.value = currentSet || "";
}

function populateType(currentType) {
  const sel = _modal.querySelector(".ed-type");
  sel.innerHTML = "";
  const blank = document.createElement("option");
  blank.value = ""; blank.textContent = "—";
  sel.appendChild(blank);
  for (const t of _state.vocab.types) {
    const o = document.createElement("option"); o.value = t; o.textContent = t;
    sel.appendChild(o);
  }
  if (currentType && !_state.vocab.types.includes(currentType)) {
    const o = document.createElement("option");
    o.value = currentType; o.textContent = currentType + " (off-vocab)";
    sel.appendChild(o);
  }
  sel.value = currentType || "";
}

function populateElement(currentList) {
  const box = _modal.querySelector(".ed-element-chips");
  box.innerHTML = "";
  const set = new Set(currentList.map(e => e.toLowerCase()));
  for (const el of _state.vocab.elements) {
    const id = `el-${el}`;
    const wrap = document.createElement("label");
    wrap.className = "ed-element-chip";
    const cb = document.createElement("input");
    cb.type = "checkbox"; cb.id = id; cb.value = el; cb.checked = set.has(el);
    cb.addEventListener("change", scheduleSave);
    const txt = document.createElement("span"); txt.textContent = el;
    wrap.appendChild(cb); wrap.appendChild(txt);
    box.appendChild(wrap);
  }
}

function toggleElementBlock(type) {
  const block = _modal.querySelector(".ed-element-block");
  const hide = type === "Commands" || type === "Skills";
  block.style.display = hide ? "none" : "";
  if (hide) {
    for (const cb of _modal.querySelectorAll(".ed-element-chips input")) {
      cb.checked = false;
    }
  }
}

function onSetChange(e) {
  if (e.target.value === "__add__") {
    const name = (window.prompt("New set name:") || "").trim();
    if (!name) {
      e.target.value = _state.cards[_state.index].set || "";
      return;
    }
    if (!_state.vocab.sets.includes(name)) {
      _state.vocab.sets.push(name);
    }
    populateSet(name);
  }
  scheduleSave();
}

function onTypeChange(e) {
  toggleElementBlock(e.target.value);
  scheduleSave();
}

function readForm() {
  const m = _modal;
  const elements = Array.from(
    m.querySelectorAll(".ed-element-chips input:checked"),
    cb => cb.value
  );
  return {
    name: m.querySelector(".ed-name").value.trim(),
    set: m.querySelector(".ed-set").value === "__add__"
            ? "" : m.querySelector(".ed-set").value,
    type: m.querySelector(".ed-type").value,
    element: elements,
  };
}

let _saveTimer = null;
function scheduleSave() {
  clearTimeout(_saveTimer);
  _saveTimer = setTimeout(doSave, 250);
}
function flushSave() {
  if (_saveTimer) {
    clearTimeout(_saveTimer);
    _saveTimer = null;
    doSave();
  }
}

async function doSave() {
  if (!_state) return;
  const card = _state.cards[_state.index];
  const payload = readForm();
  setStatus("Saving…", "saving");
  try {
    const res = await fetch(`/api/labels/${encodeURIComponent(card.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const updated = await res.json();
    _state.cards[_state.index] = updated;
    setStatus("Saved ✓", "saved");
    if (_state.onSave) _state.onSave(updated);
  } catch (err) {
    setStatus("Save failed: " + err.message, "error");
  }
}

async function openEditor(cards, index, opts) {
  opts = opts || {};
  const modal = _ensure();
  const vocab = await opts.getVocab();
  _state = {
    cards: cards.slice(),     // snapshot so filter changes don't shift us
    index,
    vocab,
    onSave: opts.onSave,
  };
  modal.classList.add("open");
  document.addEventListener("keydown", _onKey);
  loadCurrent();
  modal.querySelector(".ed-name").focus();
}

// Tiny memoized vocab fetcher; pages can pass this as opts.getVocab.
let _vocabPromise = null;
function fetchVocab() {
  if (!_vocabPromise) {
    _vocabPromise = fetch("/api/vocab").then(r => r.json());
  }
  return _vocabPromise;
}
```

- [ ] **Step 2: Append editor CSS to static/style.css**

```bash
cat >> static/style.css << 'EOF'

/* Card editor modal — replaces the old image-only zoom. */
.editor-modal {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.78);
  display: none;
  z-index: 50;
}
.editor-modal.open { display: flex; align-items: center; justify-content: center; }
.editor-stage {
  display: flex; align-items: center;
  width: min(96vw, 1600px); height: 92vh;
  gap: 12px;
}
.editor-body {
  display: flex; gap: 16px;
  flex: 1; min-width: 0; height: 100%;
}
.editor-image {
  flex: 1; min-width: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--panel);
  border-radius: 10px;
  overflow: hidden;
}
.editor-image img {
  max-width: 100%; max-height: 100%;
  object-fit: contain;
}
.editor-form {
  width: 340px;
  background: var(--panel);
  border-radius: 10px;
  padding: 16px;
  display: flex; flex-direction: column;
  gap: 12px;
  overflow-y: auto;
}
.ed-head {
  display: flex; justify-content: space-between;
  font-size: 12px; color: var(--sub);
  margin-bottom: 4px;
}
.editor-form label {
  display: flex; flex-direction: column;
  font-size: 12px; color: var(--sub); gap: 4px;
}
.editor-form input[type=text], .editor-form select {
  font: inherit; padding: 6px 8px;
  background: var(--panel2); color: var(--text);
  border: 1px solid var(--line); border-radius: 6px;
}
.ed-element-block { display: flex; flex-direction: column; gap: 6px; }
.ed-element-label { font-size: 12px; color: var(--sub); }
.ed-element-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ed-element-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--text);
  padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px;
  cursor: pointer;
}
.ed-element-chip:has(input:checked) {
  background: var(--accent); color: #0b1220;
  border-color: var(--accent);
}
.ed-status { font-size: 12px; min-height: 16px; color: var(--sub); }
.ed-status[data-kind=saved] { color: var(--good); }
.ed-status[data-kind=error] { color: var(--danger); }
.ed-nav {
  font-size: 24px; line-height: 1;
  background: transparent; border: 1px solid var(--line); color: var(--text);
  width: 44px; height: 56px; border-radius: 8px;
  cursor: pointer;
}
.ed-nav:hover:not(:disabled) { border-color: var(--accent); }
.ed-nav:disabled { opacity: 0.3; cursor: default; }

@media (max-width: 720px) {
  .editor-body { flex-direction: column; }
  .editor-form { width: auto; max-height: 40vh; }
}
EOF
echo "appended"
```

- [ ] **Step 3: Smoke the JS by parsing it with node**

Run: `node -c static/editor.js && echo "OK"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add static/editor.js static/style.css
git -c commit.gpgsign=false commit -m "Add static/editor.js — the card editor modal"
```

---

## Task 6: cards.html — wire the editor in

**Files:**
- Modify: `templates/cards.html`

Replace `setupZoom` usage with `openEditor`. On save, update the local CARDS array and re-render the grid so the tile reflects the new name immediately.

- [ ] **Step 1: Update cards.html**

In `templates/cards.html`, replace the inline `<script>` block at the bottom. Find:

```javascript
const zoom = setupZoom();
```

…and the per-tile handler:

```javascript
    tile.querySelector("img").addEventListener("click", () => zoom(c.id));
```

…and the `<script src="/static/filters.js"></script>` line.

Replace the whole `<script>` block (the one containing `let CARDS = [];`) with:

```html
<script src="/static/common.js"></script>
<script src="/static/filters.js"></script>
<script src="/static/editor.js"></script>
<script>
let CARDS = [];
const state = {
  selectedSets: new Set(),
  selectedElements: new Set(),
  selectedTypes: new Set(),
  search: "",
  hideUnlabeled: false,
};
const grid = document.getElementById("grid");

let LAST_FILTERED = [];

function render() {
  const items = CARDS.filter(c => cardPasses(c, state));
  LAST_FILTERED = items;
  grid.innerHTML = "";
  const frag = document.createDocumentFragment();
  items.forEach((c, i) => {
    const tile = document.createElement("div");
    tile.className = "card-tile";
    const primary = c.name || c.id;
    const subtitle = c.name ? `<div class="code-sub">${c.id}</div>` : "";
    tile.innerHTML = `
      <img loading="lazy" src="/api/card/${encodeURIComponent(c.id)}/thumb" alt="${primary}">
      <div class="code">${primary}</div>
      ${subtitle}`;
    tile.querySelector("img").addEventListener("click",
      () => openEditor(LAST_FILTERED, i, {
        getVocab: fetchVocab,
        onSave: (updated) => onCardSaved(updated),
      }));
    frag.appendChild(tile);
  });
  grid.appendChild(frag);
  document.getElementById("count").textContent = `${items.length} cards`;
}

function onCardSaved(updated) {
  const i = CARDS.findIndex(c => c.id === updated.id);
  if (i >= 0) CARDS[i] = updated;
  render();
}

async function load() {
  const data = await api("/api/cards");
  CARDS = data.cards;
  renderStandardChips(data, state, render);
  render();
}

document.getElementById("search").addEventListener("input", (e) => {
  state.search = e.target.value;
  render();
});
document.getElementById("hideUnlabeled").addEventListener("change", (e) => {
  state.hideUnlabeled = e.target.checked;
  render();
});
setupSizeSlider(document.getElementById("sizeRange"));
load();
watchCacheWarm(document.getElementById("warm"));
</script>
```

- [ ] **Step 2: Boot the server and verify the editor opens**

```bash
pkill -9 -f "app.py" 2>/dev/null; sleep 1
.venv/bin/python app.py > /tmp/bd-app.log 2>&1 &
disown
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/cards | grep -q 200; do sleep 1; done

# Verify the page loads with the editor wiring
curl -s http://127.0.0.1:5000/cards | grep -E "editor.js|openEditor|fetchVocab"
```

Expected: lines confirming editor.js is loaded and the openEditor / fetchVocab calls are present.

- [ ] **Step 3: Stop the server**

```bash
pkill -9 -f "app.py" 2>/dev/null; sleep 1
```

- [ ] **Step 4: Commit**

```bash
git add templates/cards.html
git -c commit.gpgsign=false commit -m "cards.html: open the editor on tile click (was image-only zoom)"
```

---

## Task 7: deck.html — wire the editor in + drop setupZoom

**Files:**
- Modify: `templates/deck.html`
- Modify: `static/common.js`

Same wiring on the deck-edit add-cards grid. Also update the side panel rendering so renaming a card immediately reflects there. Drop `setupZoom` from `static/common.js` now that nothing references it.

- [ ] **Step 1: Update deck.html**

Two edits in `templates/deck.html`:

A. Add the editor script tag below `filters.js`:

```html
<script src="/static/common.js"></script>
<script src="/static/filters.js"></script>
<script src="/static/editor.js"></script>
```

B. Replace the line:

```javascript
const zoom = setupZoom();
```

with nothing (delete the line). Also delete any other references to `zoom(...)`.

C. In `tileFor(c)`, replace the click handler line:

```javascript
  tile.querySelector("img").addEventListener("click", () => zoom(c.id));
```

with:

```javascript
  tile.querySelector("img").addEventListener("click", () => {
    const idx = LAST_FILTERED.indexOf(c);
    if (idx >= 0) openEditor(LAST_FILTERED, idx, {
      getVocab: fetchVocab,
      onSave: onCardSaved,
    });
  });
```

D. In `renderGrid()`, capture the filtered list. Replace:

```javascript
function renderGrid() {
  const items = CARDS.filter(c =>
    cardPasses(c, filterState) &&
    (!deckOnly || (counts[c.id] || 0) > 0));
```

with:

```javascript
let LAST_FILTERED = [];
function renderGrid() {
  const items = CARDS.filter(c =>
    cardPasses(c, filterState) &&
    (!deckOnly || (counts[c.id] || 0) > 0));
  LAST_FILTERED = items;
```

(Move the `let LAST_FILTERED = [];` declaration to a module-level spot near `let CARDS = [];` — not inside the function. The form shown here places it outside the function for clarity.)

E. In `renderDeckList(d)`, the image click handler:

```javascript
    row.querySelector("img").addEventListener("click", () => zoom(it.id));
```

becomes:

```javascript
    row.querySelector("img").addEventListener("click", () => {
      // Snapshot just this card so the editor can still be navigated if the
      // deck has more than one card (we walk the deck list, not the grid).
      const list = d.cards;
      const idx = list.findIndex(x => x.id === it.id);
      if (idx >= 0) openEditor(list, idx, {
        getVocab: fetchVocab, onSave: onCardSaved,
      });
    });
```

F. Add `onCardSaved` somewhere near `applyResolved`:

```javascript
function onCardSaved(updated) {
  // Update CARDS so the grid renders the new metadata next time it draws.
  const i = CARDS.findIndex(c => c.id === updated.id);
  if (i >= 0) CARDS[i] = updated;
  cardMeta[updated.id] = { set: updated.set, name: updated.name };
  // Re-render the deck side panel so the renamed card shows its new name.
  renderDeckList(localDeck());
  // And update the grid in case the edit changed how it's filtered/sorted.
  renderGrid();
}
```

G. The `localDeck()` function reads `cardMeta[id]` for set/name — already keyed by id, no changes needed.

- [ ] **Step 2: Drop setupZoom from static/common.js**

Remove the entire `setupZoom` function and its modal-creation block from `static/common.js`. The remaining file should still export `api`, `apiJSON`, `toast`, `setupSizeSlider`, `watchCacheWarm`.

- [ ] **Step 3: Smoke the page boots + the API flow**

```bash
pkill -9 -f "app.py" 2>/dev/null; sleep 1
.venv/bin/python app.py > /tmp/bd-app.log 2>&1 &
disown
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ | grep -q 200; do sleep 1; done

# Drive a label edit end-to-end via the same APIs the editor uses.
echo "--- write a label via PUT ---"
curl -s -X PUT http://127.0.0.1:5000/api/labels/BDS1-EN_0001 \
  -H 'Content-Type: application/json' \
  -d '{"name":"Phoenix","set":"Light Starter","type":"Shadows","element":["light"]}' \
  | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['name'], d['element'], d['type'])"

echo "--- /api/cards reflects it ---"
curl -s http://127.0.0.1:5000/api/cards | python3 -c "
import sys, json
d = json.load(sys.stdin)
c = next(x for x in d['cards'] if x['id']=='BDS1-EN_0001')
print(c)
"

echo "--- /api/vocab includes the seeded set + the newly-saved set (no dupe) ---"
curl -s http://127.0.0.1:5000/api/vocab | python3 -c "
import sys, json
v = json.load(sys.stdin)
print('sets count:', len(v['sets']))
print('Light Starter present:', 'Light Starter' in v['sets'])
"

# Revert the demo edit.
git checkout labels.csv

pkill -9 -f "app.py" 2>/dev/null; sleep 1
```

Expected: the PUT returns `Phoenix ['light'] Shadows`; `/api/cards` shows the new fields on that card; `/api/vocab` returns 6 sets with `Light Starter` present.

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add templates/deck.html static/common.js
git -c commit.gpgsign=false commit -m "deck.html: open the editor on tile click; drop setupZoom"
```

---

## Task 8: filters.js — chip data source switches to /api/vocab

**Files:**
- Modify: `static/filters.js`
- Modify: `templates/cards.html`
- Modify: `templates/deck.html`

Today the chip rows are sourced from `/api/cards.sets`, `.elements`, `.types`. Switch them to `/api/vocab`. The chip filtering logic stays the same.

- [ ] **Step 1: Update renderStandardChips to take a vocab argument**

In `static/filters.js`, replace the helper functions at the bottom:

```javascript
function buildChipRows(vocab) {
  return {
    set: vocab.sets || [],
    element: vocab.elements || [],
    type: vocab.types || [],
  };
}

function renderStandardChips(vocab, state, onChange) {
  const chips = buildChipRows(vocab);
  state.selectedSets = new Set();
  state.selectedElements = new Set();
  state.selectedTypes = new Set();
  renderChipRow(document.getElementById("chipSet"), "Set",
                chips.set, state.selectedSets, onChange);
  renderChipRow(document.getElementById("chipElement"), "Element",
                chips.element, state.selectedElements, onChange);
  renderChipRow(document.getElementById("chipType"), "Type",
                chips.type, state.selectedTypes, onChange);
}
```

(Same shape as before — the function just now receives a vocab object instead of the `/api/cards` payload.)

- [ ] **Step 2: cards.html — fetch vocab and pass it to renderStandardChips**

In `templates/cards.html`, replace the `load()` function:

```javascript
async function load() {
  const [data, vocab] = await Promise.all([
    api("/api/cards"),
    fetchVocab(),
  ]);
  CARDS = data.cards;
  renderStandardChips(vocab, state, render);
  render();
}
```

- [ ] **Step 3: deck.html — same change inside init()**

In `templates/deck.html`, inside `init()`, replace the part that calls `renderStandardChips(cards, ...)`:

```javascript
    const [deck, cards, vocab] = await Promise.all([
      api(`/api/decks/${encodeURIComponent(DECK_ID)}`),
      api("/api/cards"),
      fetchVocab(),
    ]);
    CARDS = (cards && cards.cards) || [];
    cardMeta = {};
    for (const c of CARDS) cardMeta[c.id] = { set: c.set, name: c.name };
    renderStandardChips(vocab, filterState, renderGrid);
```

- [ ] **Step 4: Functional check**

```bash
node -c static/filters.js && echo "filters.js OK"

pkill -9 -f "app.py" 2>/dev/null; sleep 1
.venv/bin/python app.py > /tmp/bd-app.log 2>&1 &
disown
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ | grep -q 200; do sleep 1; done

# The browse page should now reference /api/vocab in addition to /api/cards.
curl -s http://127.0.0.1:5000/cards | grep -E "fetchVocab|renderStandardChips"

pkill -9 -f "app.py" 2>/dev/null; sleep 1
```

Expected: filters.js parses; the page references both `fetchVocab` and `renderStandardChips`.

- [ ] **Step 5: Run all tests**

Run: `.venv/bin/pytest -q 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add static/filters.js templates/cards.html templates/deck.html
git -c commit.gpgsign=false commit -m "Filter chips sourced from /api/vocab (was data-derived)"
```

---

## Task 9: README + end-to-end smoke + final polish

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README's "Card labels" section**

In `README.md`, find the "Card labels" section. Replace it with:

```markdown
## Card labels

Metadata for the card scans lives in `labels.csv` at the repo root. Columns are
`id, set, name, element, type`. This file is committed; if your scans match the
maintainer's, you'll get name search and element/type filters for free. If
your scans differ, you can edit `labels.csv` directly — or label cards from
inside the app.

**Labeling from inside the app.** Click any card thumbnail (on Browse Cards or
Edit Deck) and the card opens at full size with an editor panel alongside.
Pick a Type, a Set, and the Element(s); changes autosave back to `labels.csv`.
Walk between cards in the current filtered view with ◀ / ▶ (or the arrow keys)
for batch labeling.

Vocabularies:

- **Type**: Shadows, Partners, Skills, Commands.
- **Element / attribute**: light, dark, fire, water, earth, wind, none.
  Only Shadows and Partners carry an element; the editor hides the element
  block for Commands and Skills.
- **Set**: the six original sets, plus anything you add via the "+ Add new
  set…" entry in the Set dropdown.

Cards with no `labels.csv` row still appear in the browse grid — they show
their ID instead of a printed name and don't match any chip filter. The
"Hide unlabeled" toggle removes them from the grid entirely.
```

- [ ] **Step 2: End-to-end smoke — boot, label five cards via the API, verify the CSV**

```bash
pkill -9 -f "app.py" 2>/dev/null; sleep 1
.venv/bin/python app.py > /tmp/bd-app.log 2>&1 &
disown
until curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/ | grep -q 200; do sleep 1; done

put() {
  local cid="$1" name="$2" set="$3" type="$4" element="$5"
  curl -s -X PUT "http://127.0.0.1:5000/api/labels/$cid" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"$name\",\"set\":\"$set\",\"type\":\"$type\",\"element\":$element}" \
    > /dev/null
}

put BDS1-EN_0001 Phoenix       "Light Starter" Shadows  '["light"]'
put BDS1-EN_0002 Jiro          "Light Starter" Partners '["earth"]'
put BDS2-EN_0001 Minotaur      "Shadow Starter" Shadows '["dark"]'
put BD01-EN_0010 "Two-faced"   "Set 1"          Shadows '["light","dark"]'
put BD01-EN_0099 "Lightning"   "Set 1"          Commands '["fire"]'
# Note the Commands row sent fire — server should clear it.

echo "--- labels.csv contents ---"
cat labels.csv

echo "--- /api/cards reflects them ---"
curl -s http://127.0.0.1:5000/api/cards | python3 -c "
import sys, json
d = json.load(sys.stdin)
ids = {'BDS1-EN_0001','BDS1-EN_0002','BDS2-EN_0001','BD01-EN_0010','BD01-EN_0099'}
for c in d['cards']:
    if c['id'] in ids:
        print(c['id'], '->', c['name'], c['set'], c['type'], c['element'])
"

# Revert the demo edits so we don't commit anything personal.
git checkout labels.csv

pkill -9 -f "app.py" 2>/dev/null; sleep 1
```

Expected:
- The CSV shows five new rows, alphabetically sorted by id.
- `BD01-EN_0099` (the Command) has an empty element cell.
- `BD01-EN_0010` (Two-faced) shows `dark|light` in the element cell.
- The `/api/cards` output prints each card with name, set, type, and the element list. The Command row prints `element: []`.

- [ ] **Step 3: Run all tests one more time**

Run: `.venv/bin/pytest -q 2>&1 | tail -3`
Expected: all pass (target rough count: 25+).

- [ ] **Step 4: Verify the working tree is clean except for README**

```bash
git status -s
```

Expected: only `M README.md` and `?? docs/superpowers/plans/2026-06-17-card-labeling-ui.md`.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/plans/2026-06-17-card-labeling-ui.md
git -c commit.gpgsign=false commit -m "README + implementation plan for in-UI labeling editor"
```

---

## Done state

- Click a card → modal opens with image dominant + form on the right.
- Form fields: Name, Set (dropdown + "+ Add new set"), Type (dropdown), Element (checkboxes — visible only for Shadows / Partners).
- Autosave on every change; status line shows Saving / Saved / Save failed.
- ◀ / ▶ + arrow keys walk the current filtered list of cards.
- Saved changes persist to `labels.csv` (atomic write, sorted by id, multi-element joined with `|`).
- Filter chip rows now come from `/api/vocab` — all canonical values always show.
- Per-card `element` is a list of strings across the API and in the filter pipeline.
- Tests cover: pipe-separated parse, lenient warnings, dump round-trip, dump atomicity, save_label create/update/Commands-clear/concurrent.

Out of scope by design: OCR / automation script (separate spec), foil-card handling, multi-tab real-time sync, undo/redo, bulk edit.
