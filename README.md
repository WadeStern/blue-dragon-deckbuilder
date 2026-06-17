# Blue Dragon Deck Builder

A small **local** web app for building decks for the Blue Dragon trading card
game and exporting a single shareable image of the deck (staggered card stacks
with copy counts).

Everything runs on your own machine. Nothing is uploaded anywhere, and your
card images never leave your disk.

---

## Features

- Browse all cards with chip-based filters (set / type / element) and a
  combined name/code search.
- In-app card editor: click a card to read it at full size and correct its
  metadata; ◀ ▶ keys walk through the current filtered view.
- Multi-set support — a card that was reprinted in two starter decks shows
  up under both set chips.
- Build multiple decks (each saved as a JSON file under `decks/`) with the
  3-copies-per-card limit and a target deck size.
- Export your deck as a single staggered-stack image (kept small so it's
  easy to share), or as a plain-text decklist that another user can
  import to get an identical deck.

---

## Setup

You need three things: Python, this repo, and the card pack.

1. **Install Python 3.10 or newer.** <https://www.python.org/downloads/>
   (on Windows tick *"Add Python to PATH"* during install).
2. **Clone this repo.**
   ```bash
   git clone https://github.com/<your-fork>/blue-dragon-deckbuilder.git
   cd blue-dragon-deckbuilder
   ```
3. **Install the Python dependencies.**
   ```bash
   pip install -r requirements.txt
   ```
4. **Get the card image pack** from the maintainer. The card scans are
   **not** committed to this repo (they're copyrighted by the publisher) —
   contact the maintainer to request access. The pack is a folder of JPEGs;
   the filename stem of each image is its card ID
   (e.g. `BDS1-EN_0008.jpg` → card `BDS1-EN_0008`).
5. **Drop the images into `<repo>/cards/`.** That folder is gitignored, so
   the images never accidentally end up in a commit.
6. **Run the app.**
   ```bash
   python app.py
   ```
   Then open <http://127.0.0.1:5000>.

On Windows you can double-click `run.bat` instead of running `python app.py`.

---

## Using the app

- **Home (Decks)** — create, open, or delete decklists. Each deck is saved
  as a small JSON file in `decks/`.
- **Browse Cards** — scrolls every card in the collection. Filter by chip
  rows (Set / Element / Type) and a name/code text box. Click a card to
  open the editor.
- **Edit Deck** — the left panel is a filtered card grid with `− n +`
  controls to set how many copies to run; the right panel is the live
  decklist with a `37 / 40` counter and a `⬇ Download deck image` button.
- **Card editor** — opens whenever you click a card thumbnail. Shows the
  card at full size with a form for Name / Set / Type / Attribute. Edits
  autosave; `◀ ▶` (or arrow keys) walk to the previous / next card in
  whatever list you opened from. `Esc` or the `×` button closes.

The exported deck image lays out every unique card in a grid, fans
duplicate copies behind the front card with an `×N` badge, and is
automatically scaled and compressed so it stays small.

---

## How the metadata works

Card metadata lives in `labels.csv` at the repo root. Columns:
`id, set, name, element, type`. Both `set` and `element` can be multi-valued
(pipe-separated in the CSV — e.g. `Set 2|Parallel Shadows` or `light|dark`).
This file is committed so the labels are shared with every user of the
canonical card pack.

Vocabularies the editor uses:

| Field | Allowed values |
|-------|---|
| Type | Shadow, Partner, Skill, Command |
| Attribute / element | light, dark, fire, water, earth, wind, none |
| Set | Light Starter, Shadow Starter, Demo Deck, Set 1, Set 2, Parallel Shadows (and any custom set you add via "+ new") |

Only Shadow and Partner cards carry an attribute — the editor hides the
attribute block for Skills and Commands. Cards with no `labels.csv` row
still appear in the browse grid (shown by their ID); the "Hide unlabeled"
toggle removes them from the grid entirely.

---

## Configuration overrides (optional)

By default the app looks for cards at `./cards/` and labels at
`./labels.csv`. Override with **either**:

1. An environment variable: `BD_CARDS_DIR=/path/to/cards` or
   `BD_LABELS_PATH=/path/to/labels.csv`.
2. A `config.local.json` next to `app.py`:
   ```json
   { "cards_dir": "/path/to/your/cards", "labels_path": "/path/to/labels.csv" }
   ```

Other knobs available in `config.local.json`:

| Key | Default | Meaning |
|-----|---------|---------|
| `cards_dir` | `./cards` | Path to the flat folder of card images |
| `labels_path` | `./labels.csv` | Path to the labels CSV |
| `max_copies_per_card` | `3` | Deck rule: max copies of one card |
| `deck_target_size` | `40` | Deck size the counter aims for |
| `export_max_bytes` | `10485760` | Upper bound the image-export auto-shrink targets |
| `prewarm_thumbs` | `true` | Build the thumbnail cache in the background on startup so browsing is instant |
| `prewarm_views` | `false` | Also pre-build the larger zoom/export cache (~250 MB; only speeds up first zoom/export) |

`config.local.json` is gitignored, so each user can set their own paths
without polluting the repo.

---

## Project layout

```
.
├── app.py              Flask app + HTTP routes
├── catalog.py          In-memory card catalog; loads + writes labels.csv
├── config.py           Resolves paths and reads config.local.json
├── decks.py            Per-deck JSON persistence and deck-rule enforcement
├── labels.py           labels.csv parser and dumper
├── render.py           Deck-image export (PIL)
├── vocab.py            Locked type/element/set vocabularies
├── labels.csv          Card metadata (committed)
├── cards/              Card images (gitignored)
├── decks/              Saved decklists (gitignored)
├── cache/              Generated thumbnails (gitignored)
├── templates/          Jinja templates
├── static/             JS + CSS
├── scripts/            Maintainer-only utilities (see below)
└── tests/              pytest suite
```

### Maintainer tools

The `scripts/` folder contains one-off utilities that the maintainer uses
when curating the card pack — they're **not** part of the normal
end-user workflow:

- `scripts/flatten_cards.py` — flattens a nested per-set scan tree into
  one flat folder. Useful when ingesting a new batch of scans.
- `scripts/dedupe_cards.py` — finds duplicate images via byte hash or
  perceptual hash (`--perceptual`), shows a removal plan, and on `--apply`
  consolidates them. Run with `--help` for options.

Each script defaults to dry-run; pass `--apply` to actually mutate anything.

---

## Development

Run the tests:

```bash
pytest -q
```

The test suite covers the labels parser/dumper, the catalog scan, deck
persistence, and the image-flatten script. No browser-level tests — UI
changes are smoke-tested manually.

---

## Privacy

Nothing in the app talks to the network. The Flask server binds to
`127.0.0.1` only, deck JSONs live in `decks/`, and the thumbnail cache
lives in `cache/`. Card images, decks, and the thumbnail cache are all
gitignored so they never leak through commits.

---

## Credits

Card scans this project was built around were originally shared by
**u/The-Red-Comet00** on Reddit — thank you for making the catalog
accessible to the community.

---

## Disclaimer

This is an **unofficial, non-commercial, fan-made** tool with no affiliation
with — and no endorsement by — the creators, publishers, or rights holders of
the Blue Dragon trading card game or franchise. **Blue Dragon**, its card
images, names, artwork, and all related assets are the property of their
respective owners. This repository contains **no** card images or game assets;
users must supply their own from cards they legally own.

## License

Application source code is released under the **MIT License** — see
[`LICENSE`](LICENSE). The license covers the code only, not any game assets.
