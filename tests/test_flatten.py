import os
import shutil

import pytest

from scripts import flatten_cards


def make_source(tmp_path):
    """Build a nested per-set source folder and return (root, expected_files)."""
    root = tmp_path / "English"
    (root / "Light Starter").mkdir(parents=True)
    (root / "Shadow Starter").mkdir(parents=True)
    (root / "Light Starter" / "BDS1-EN_0001.jpg").write_bytes(b"a")
    (root / "Light Starter" / "BDS1-EN_0002.jpg").write_bytes(b"b")
    (root / "Shadow Starter" / "BDS2-EN_0001.jpg").write_bytes(b"c")
    (root / "Light Starter" / "notes.txt").write_text("non-image")
    return str(root), ["BDS1-EN_0001.jpg", "BDS1-EN_0002.jpg", "BDS2-EN_0001.jpg"]


def test_plan_lists_every_image(tmp_path):
    src, expected = make_source(tmp_path)
    dst = str(tmp_path / "cards")
    plan = flatten_cards.build_plan(src, dst)
    src_names = sorted(os.path.basename(p.src) for p in plan)
    assert src_names == sorted(expected)
    for entry in plan:
        assert entry.dst.startswith(dst)


def test_collision_across_sets_raises(tmp_path):
    src, _ = make_source(tmp_path)
    (tmp_path / "English" / "Shadow Starter" / "BDS1-EN_0001.jpg").write_bytes(b"dup")
    with pytest.raises(flatten_cards.CollisionError) as exc:
        flatten_cards.build_plan(src, str(tmp_path / "cards"))
    assert "BDS1-EN_0001.jpg" in str(exc.value)


def test_apply_copies_files(tmp_path):
    src, expected = make_source(tmp_path)
    dst = tmp_path / "cards"
    plan = flatten_cards.build_plan(src, str(dst))
    flatten_cards.apply(plan, move=False, force=False)
    assert sorted(p.name for p in dst.iterdir()) == sorted(expected)
    # source untouched
    assert (tmp_path / "English" / "Light Starter" / "BDS1-EN_0001.jpg").exists()


def test_apply_is_idempotent_on_identical_bytes(tmp_path):
    src, _ = make_source(tmp_path)
    dst = tmp_path / "cards"
    plan = flatten_cards.build_plan(src, str(dst))
    flatten_cards.apply(plan, move=False, force=False)
    # second run: identical destination contents, should be a no-op (no exception)
    flatten_cards.apply(plan, move=False, force=False)


def test_apply_errors_on_byte_mismatch_without_force(tmp_path):
    src, _ = make_source(tmp_path)
    dst = tmp_path / "cards"
    dst.mkdir()
    (dst / "BDS1-EN_0001.jpg").write_bytes(b"DIFFERENT")
    plan = flatten_cards.build_plan(src, str(dst))
    with pytest.raises(flatten_cards.DestinationConflict):
        flatten_cards.apply(plan, move=False, force=False)


def test_apply_force_overwrites_mismatch(tmp_path):
    src, _ = make_source(tmp_path)
    dst = tmp_path / "cards"
    dst.mkdir()
    (dst / "BDS1-EN_0001.jpg").write_bytes(b"DIFFERENT")
    plan = flatten_cards.build_plan(src, str(dst))
    flatten_cards.apply(plan, move=False, force=True)
    assert (dst / "BDS1-EN_0001.jpg").read_bytes() == b"a"


def test_move_deletes_source(tmp_path):
    src, _ = make_source(tmp_path)
    dst = tmp_path / "cards"
    plan = flatten_cards.build_plan(src, str(dst))
    flatten_cards.apply(plan, move=True, force=False)
    assert not (tmp_path / "English" / "Light Starter" / "BDS1-EN_0001.jpg").exists()


def test_exclude_skips_subfolder(tmp_path):
    src, _ = make_source(tmp_path)
    # Drop a non-card subfolder into the source.
    extras = tmp_path / "English" / "Strategies & Tips"
    extras.mkdir()
    (extras / "strategy_01.jpg").write_bytes(b"strat")
    plan = flatten_cards.build_plan(
        src, str(tmp_path / "cards"), exclude=("Strategies & Tips",))
    names = sorted(os.path.basename(p.src) for p in plan)
    assert "strategy_01.jpg" not in names
