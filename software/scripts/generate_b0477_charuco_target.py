"""Generate the workcell-sized B0477 ChArUco target as a deterministic A4 PDF."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEFINITION = ROOT / "software/config/charuco_b0477_10x7_25mm_17_5mm.json"
DEFAULT_OUTPUT = ROOT / "output/pdf/b0477_charuco_10x7_25mm_17_5mm_a4.pdf"
MM_TO_PT = 72.0 / 25.4


def load_definition(path: Path) -> dict[str, Any]:
    definition = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema": "rocell.physical_charuco_target.v1",
        "kind": "CHARUCO",
        "dictionary": "DICT_5X5_1000",
        "squares_x": 10,
        "squares_y": 7,
        "square_length_mm": 25.0,
        "marker_length_mm": 17.5,
        "board_width_mm": 250.0,
        "board_height_mm": 175.0,
        "border_bits": 1,
    }
    for key, value in expected.items():
        if definition.get(key) != value:
            raise ValueError(f"target definition mismatch: {key}")
    contract = definition.get("print_contract", {})
    if contract.get("page") != "A4_LANDSCAPE" or contract.get("scale_percent") != 100.0:
        raise ValueError("target must retain the reviewed A4 1:1 print contract")
    return definition


def generate_pdf(definition: dict[str, Any], output: Path) -> str:
    import cv2
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_1000)
    board = cv2.aruco.CharucoBoard(
        (definition["squares_x"], definition["squares_y"]),
        definition["square_length_mm"] / 1000.0,
        definition["marker_length_mm"] / 1000.0,
        dictionary,
    )
    raster = board.generateImage((5000, 3500), marginSize=0, borderBits=1)
    ok, encoded = cv2.imencode(".png", raster, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OpenCV could not encode the generated target")

    page_width = 297.0 * MM_TO_PT
    page_height = 210.0 * MM_TO_PT
    board_width = definition["board_width_mm"] * MM_TO_PT
    board_height = definition["board_height_mm"] * MM_TO_PT
    x = (page_width - board_width) / 2.0
    y = (page_height - board_height) / 2.0
    output.parent.mkdir(parents=True, exist_ok=True)
    document = canvas.Canvas(
        str(output), pagesize=(page_width, page_height), invariant=1,
        pageCompression=0,
    )
    document.drawImage(
        ImageReader(io.BytesIO(encoded.tobytes())), x, y,
        width=board_width, height=board_height, mask=None,
    )
    document.setFont("Helvetica", 6)
    document.drawCentredString(
        page_width / 2.0, page_height - 8.0,
        "B0477 CHARUCO 10x7 | 25.000 mm squares | 17.500 mm markers | PRINT 100% / ACTUAL SIZE",
    )
    document.setLineWidth(0.35)
    scale_x = 14.0 * MM_TO_PT
    scale_y0 = y + 37.5 * MM_TO_PT
    scale_y1 = scale_y0 + 100.0 * MM_TO_PT
    document.line(scale_x, scale_y0, scale_x, scale_y1)
    document.line(scale_x - 2.0 * MM_TO_PT, scale_y0, scale_x + 2.0 * MM_TO_PT, scale_y0)
    document.line(scale_x - 2.0 * MM_TO_PT, scale_y1, scale_x + 2.0 * MM_TO_PT, scale_y1)
    document.save()
    payload = output.read_bytes()
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", type=Path, default=DEFAULT_DEFINITION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    definition = load_definition(args.definition.resolve())
    digest = generate_pdf(definition, args.output.resolve())
    print(json.dumps({"path": str(args.output.resolve()), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
