"""One-time migration: copy card images from a nested per-set source folder
into a single flat destination folder.

Default behavior is dry-run (prints the plan, no disk changes). Use --apply
to copy, --move to copy-then-delete-source, --force to overwrite a destination
file that exists with different bytes.

Run via:  python -m scripts.flatten_cards --source <path> [options]
"""
import argparse
import filecmp
import os
import shutil
import sys
from dataclasses import dataclass


IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
DEFAULT_EXCLUDED_SUBFOLDERS = ("Strategies & Tips",)


class CollisionError(RuntimeError):
    """Two source files would land on the same destination filename."""


class DestinationConflict(RuntimeError):
    """Destination file exists with different bytes and --force was not passed."""


@dataclass(frozen=True)
class PlanEntry:
    src: str
    dst: str


def _is_image(name):
    _, ext = os.path.splitext(name)
    return ext.lower() in IMAGE_EXTS


def build_plan(source, dest, exclude=()):
    """Walk `source` (one level of subdirs) and produce the list of
    src->dst copies that would flatten it into `dest`.

    Subfolders whose name appears in `exclude` are skipped entirely.

    Raises CollisionError if any filename appears in more than one subdir.
    """
    if not os.path.isdir(source):
        raise FileNotFoundError(f"source not found: {source}")

    excluded = set(exclude)
    seen = {}                       # basename -> src abs path
    for entry in sorted(os.listdir(source)):
        sub = os.path.join(source, entry)
        if not os.path.isdir(sub) or entry in excluded:
            continue
        for fname in sorted(os.listdir(sub)):
            if not _is_image(fname):
                continue
            src = os.path.join(sub, fname)
            if fname in seen:
                raise CollisionError(
                    f"{fname} appears in both "
                    f"{os.path.dirname(seen[fname])} and {sub}"
                )
            seen[fname] = src

    return [PlanEntry(src=src, dst=os.path.join(dest, name))
            for name, src in sorted(seen.items())]


def _files_match(a, b):
    return os.path.isfile(b) and filecmp.cmp(a, b, shallow=False)


def apply(plan, move, force):
    """Execute the plan. Copies (or moves) each src->dst; idempotent when the
    destination matches; raises DestinationConflict on mismatch unless force."""
    if not plan:
        return
    os.makedirs(os.path.dirname(plan[0].dst), exist_ok=True)
    for entry in plan:
        os.makedirs(os.path.dirname(entry.dst), exist_ok=True)
        if os.path.isfile(entry.dst):
            if _files_match(entry.src, entry.dst):
                if move:
                    os.remove(entry.src)
                continue
            if not force:
                raise DestinationConflict(
                    f"{entry.dst} exists with different bytes; pass --force to overwrite"
                )
        if move:
            shutil.move(entry.src, entry.dst)
        else:
            shutil.copy2(entry.src, entry.dst)


def _print_plan(plan, dest):
    print(f"Source files: {len(plan)}")
    print(f"Destination : {os.path.abspath(dest)}")
    for entry in plan:
        print(f"  {entry.src}  ->  {entry.dst}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="Folder containing per-set subfolders of card images.")
    parser.add_argument("--dest", default=None,
                        help="Flat destination folder. Defaults to <repo>/cards/.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually copy files (default: dry-run).")
    parser.add_argument("--move", action="store_true",
                        help="Delete the source file after each successful copy.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite destination files with differing bytes.")
    parser.add_argument("--exclude", action="append", default=None,
                        help=("Subfolder name to skip. Repeat for multiple. "
                              f"Default: {list(DEFAULT_EXCLUDED_SUBFOLDERS)}."))
    args = parser.parse_args(argv)

    exclude = (DEFAULT_EXCLUDED_SUBFOLDERS if args.exclude is None
               else tuple(args.exclude))

    if args.dest is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        args.dest = os.path.join(repo_root, "cards")

    try:
        plan = build_plan(args.source, args.dest, exclude=exclude)
    except (FileNotFoundError, CollisionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if not args.apply:
        _print_plan(plan, args.dest)
        print("\n(dry-run) pass --apply to copy these files.")
        return 0

    try:
        apply(plan, move=args.move, force=args.force)
    except DestinationConflict as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    print(f"Applied: {len(plan)} files -> {os.path.abspath(args.dest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
