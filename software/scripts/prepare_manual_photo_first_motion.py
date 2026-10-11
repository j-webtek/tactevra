"""Bind a manual scene photo and emit a no-I/O first-motion preflight."""
import argparse
import json
from pathlib import Path

from rocell.application.manual_photo_first_motion_prep import write_preflight


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photo", type=Path, required=True)
    parser.add_argument("--annotation", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(write_preflight(args.annotation, args.profile, args.photo,
                                     args.output), indent=2))
