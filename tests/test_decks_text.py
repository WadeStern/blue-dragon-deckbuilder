"""Round-trip tests for the deck text export/import format."""
import importlib

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Two real card images, two labels, an empty decks dir."""
    cards = tmp_path / "cards"; cards.mkdir()
    decks_dir = tmp_path / "decks"; decks_dir.mkdir()
    for fname in ("BDS1-EN_0001.jpg", "BDS1-EN_0008.jpg"):
        (cards / fname).write_bytes(b"x")

    (tmp_path / "labels.csv").write_text(
        "id,set,name,element,type\n"
        "BDS1-EN_0001,Light Starter,Phoenix,light,Shadow\n"
        "BDS1-EN_0008,Light Starter,Jiro,earth,Partner\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BD_CARDS_DIR", str(cards))
    monkeypatch.setenv("BD_LABELS_PATH", str(tmp_path / "labels.csv"))

    import config, catalog, decks
    importlib.reload(config)
    importlib.reload(catalog)
    importlib.reload(decks)
    monkeypatch.setattr(config, "DECKS_DIR", str(decks_dir))
    catalog.build()
    return decks


def test_export_text_contains_header_and_rows(env):
    decks = env
    deck = decks.create("My Cool Deck")
    decks.update(deck["id"], cards={"BDS1-EN_0001": 3, "BDS1-EN_0008": 2})
    text = decks.export_text(deck["id"])
    assert text is not None
    assert 'My Cool Deck' in text
    assert "5 cards" in text
    assert "2 unique" in text
    assert "BDS1-EN_0001" in text
    assert "Phoenix" in text
    assert "BDS1-EN_0008" in text
    assert "Jiro" in text


def test_export_text_missing_deck_returns_none(env):
    assert env.export_text("nope") is None


def test_import_round_trip(env):
    decks = env
    src = decks.create("Original")
    decks.update(src["id"], cards={"BDS1-EN_0001": 3, "BDS1-EN_0008": 2})
    text = decks.export_text(src["id"])

    imported, warnings = decks.import_text(text)
    assert imported is not None
    assert warnings == []
    assert imported["name"] == "Original"  # picked up from comment
    assert imported["cards"] == {"BDS1-EN_0001": 3, "BDS1-EN_0008": 2}


def test_import_explicit_name_wins(env):
    decks = env
    text = "1  BDS1-EN_0001  Phoenix\n"
    imported, _ = decks.import_text(text, name="Custom Name")
    assert imported["name"] == "Custom Name"


def test_import_skips_unknown_ids_with_warning(env):
    decks = env
    text = (
        "1  BDS1-EN_0001  Phoenix\n"
        "2  BDS9-EN_9999  Nope\n"
    )
    imported, warnings = decks.import_text(text)
    assert imported["cards"] == {"BDS1-EN_0001": 1}
    assert any("BDS9-EN_9999" in w for w in warnings)


def test_import_caps_copies(env):
    import config
    decks = env
    text = f"{config.MAX_COPIES_PER_CARD + 5}  BDS1-EN_0001  Phoenix\n"
    imported, _ = decks.import_text(text)
    assert imported["cards"]["BDS1-EN_0001"] == config.MAX_COPIES_PER_CARD


def test_import_empty_payload_returns_none(env):
    deck, warnings = env.import_text("# only a comment\n")
    assert deck is None
    assert any("no recognisable" in w for w in warnings)


def test_import_handles_extra_whitespace_and_trailing_text(env):
    decks = env
    text = "  2   BDS1-EN_0001   Phoenix (the bird)\n"
    imported, warnings = decks.import_text(text)
    assert imported["cards"] == {"BDS1-EN_0001": 2}
    assert warnings == []
