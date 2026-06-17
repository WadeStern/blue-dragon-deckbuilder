# 🐉 Blue Dragon Deck Builder

A small **local** web app for building decks for the Blue Dragon trading card
game and exporting a single shareable image of the deck (staggered card stacks
with copy counts), auto-sized to stay under Discord's 10 MB limit.

Everything runs on your own machine — nothing is uploaded anywhere, and your
card images never leave your disk.

---

## What you need

1. **Python 3.10+** — <https://www.python.org/downloads/> (tick *"Add Python to
   PATH"* during install).
2. **The card image scans.** These are **not** included in this repo. You need a
   folder that contains one sub-folder per set, each full of card images, e.g.:

   ```
   English/
     Light Starter/      BDS1-EN_0001.jpg ...
     Shadow Starter/     BDS2-EN_0001.jpg ...
     Demo Deck/          BDH1-EN_0001.jpg ...
     Set 1/              BD01-EN_0001.jpg ...
     Set 2/              BD02-EN_0001.jpg ...
     Parallel Shadows/   ...
     Strategies & Tips/  (ignored — not cards)
   ```

   Each sub-folder name becomes a selectable **set / product of origin**. Image
   filenames (without extension) become the card codes shown in the app.

### Recommended layout (zero-config)

Clone this repo **next to** your `English` card folder, so they sit side by side.
With this layout the app finds the images automatically (its default card path is
`../English`) and you don't need to configure anything:

```
BlueDragon/
  English/                     <- your card images (one sub-folder per set)
  blue-dragon-deckbuilder/     <- this repo (run it from here)
```

If your images live somewhere else, point the app at them using either method in
the next section.

---

## Configure the card folder

The app finds your card images using the **first** of these that is set:

1. Environment variable **`BD_CARDS_DIR`**
2. A file named **`config.local.json`** next to `app.py`:
   ```json
   { "cards_dir": "C:/path/to/BlueDragon/English" }
   ```
3. Default: a folder named `English` sitting next to the app folder
   (`../English`).

> Tip: copy `config.example.json` to `config.local.json` and edit the path.
> `config.local.json` is git-ignored, so everyone can set their own path.

Optional keys in `config.local.json`:

| Key | Default | Meaning |
|-----|---------|---------|
| `cards_dir` | `../English` | Path to the folder of set sub-folders |
| `excluded_sets` | `["Strategies & Tips"]` | Folder names to skip (non-card material) |
| `max_copies_per_card` | `3` | Deck rule: max copies of one card |
| `deck_target_size` | `40` | Deck size the counter aims for |
| `export_max_bytes` | `10485760` | Image export size cap (10 MB) |
| `prewarm_thumbs` | `true` | Build the thumbnail cache in the background on startup so browsing is instant |
| `prewarm_views` | `false` | Also pre-build the larger zoom/export cache (~250 MB; only speeds up first zoom/export) |

---

## Run it

- **Windows:** double-click **`run.bat`** (installs dependencies on first run,
  then launches and opens your browser).
- **Any OS / manual:**
  ```bash
  pip install -r requirements.txt
  python app.py
  ```
  Then open <http://127.0.0.1:5000>.

---

## Using the app

- **Decks** (home) — create, open, or delete decklists. Each deck is saved as a
  JSON file in `decks/`.
- **Browse Cards** — scroll all cards, filter by set, type a code to filter,
  click any card to zoom in and read it.
- **Edit a deck** — left panel is the card browser with `− n +` controls to set
  how many copies to run; right panel shows your decklist with live counts, a
  `37 / 40` counter, per-card trim/remove, and **⬇ Download deck image**.

The exported image lays out every unique card in a grid, fans duplicate copies
behind the front card with an `×N` badge, and is automatically scaled/compressed
to fit under the size limit.

---

## What is and isn't in this repo

This is just the application code. The `.gitignore` keeps the following **out** of
the repository, so nothing personal or copyrighted is published:

- **Card images** (`*.jpg/*.jpeg/*.png`, the `English/` folder) — bring your own.
- **Your decklists** (`decks/*.json`) — they stay on your machine.
- **The thumbnail/view cache** (`cache/`) — rebuilt automatically.
- **Your local card path** (`config.local.json`) — each user sets their own.

To use it, clone the repo, point it at your own card images (see *Configure the
card folder* above), and run it. You need Python and your own copy of the scans.

## Roadmap

- Card naming/labelling + search by name (currently filter by set + code).
- Optional `.exe` bundle so friends don't need Python installed.
