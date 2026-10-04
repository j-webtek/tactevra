"""Materialize and train the frozen residual-obstruction pretraining campaign."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import random
import struct
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


FIXTURE_SCHEMA = "tactevra.ai_residual_obstruction_campaign_fixture.v1"
DATASET_SCHEMA = "tactevra.ai_residual_obstruction_dataset.v1"
RESULT_SCHEMA = "tactevra.ai_residual_obstruction_development.v1"
MODEL_MAGIC = b"TACTEVRA_RESIDUAL_CNN_V1\0"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def load_bound(path: Path, schema: str, hash_field: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise ValueError(f"unsupported schema in {path}")
    claimed = payload.get(hash_field)
    core = {key: value for key, value in payload.items() if key != hash_field}
    if claimed != sha256_bytes(canonical(core)):
        raise ValueError(f"canonical hash mismatch in {path}")
    return payload


def _crop_geometry(row: dict[str, Any]) -> tuple[float, float, float, float]:
    polygon = row["target_safe_polygon_px"]
    xs = [float(point[0]) for point in polygon]
    ys = [float(point[1]) for point in polygon]
    extent = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    side = extent * float(row["crop_margin_fraction"])
    cx, cy = (float(value) for value in row["target_center_px"])
    return cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2


def _local_polygon(row: dict[str, Any], box: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    out_w, out_h = row["crop_size_px"]
    return [
        ((float(x) - left) * out_w / width, (float(y) - top) * out_h / height)
        for x, y in row["target_safe_polygon_px"]
    ]


def _rotated_bar(size: tuple[int, int], angle: float, width_fraction: float, color: tuple[int, int, int, int]) -> Image.Image:
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bar_width = max(4, round(width * width_fraction))
    draw.rectangle((width // 2 - bar_width // 2, -height, width // 2 + bar_width // 2, height * 2), fill=color)
    return layer.rotate(angle, resample=Image.Resampling.BICUBIC, center=(width / 2, height / 2))


def render_observation(row: dict[str, Any], source_image: Image.Image) -> Image.Image:
    box = _crop_geometry(row)
    size = tuple(int(value) for value in row["crop_size_px"])
    crop = source_image.crop(box).resize(size, Image.Resampling.BICUBIC).convert("RGB")
    spec = row["render_spec"]
    kind = spec["kind"]
    if kind == "IDENTITY":
        return crop

    width, height = size
    local_polygon = _local_polygon(row, box)
    center_x = sum(point[0] for point in local_polygon) / len(local_polygon)
    center_y = sum(point[1] for point in local_polygon) / len(local_polygon)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    angle = float(spec.get("rotation_deg", 0.0))

    if kind == "ADJACENT_DISTRACTOR":
        offset_x, offset_y = spec["offset_target_widths"]
        key_width = max(point[0] for point in local_polygon) - min(point[0] for point in local_polygon)
        key_height = max(point[1] for point in local_polygon) - min(point[1] for point in local_polygon)
        cx = center_x + float(offset_x) * key_width
        cy = center_y + float(offset_y) * key_height
        draw.rounded_rectangle((cx - 7, cy - 7, cx + 7, cy + 7), radius=3, fill=(40, 47, 58, 235), outline=(170, 178, 190, 230), width=2)
    elif kind == "CURVED_CABLE":
        bend = 10.0 * math.sin(math.radians(angle))
        points = [(0, center_y - bend), (width * 0.35, center_y + bend), (width * 0.65, center_y - bend), (width, center_y + bend)]
        draw.line(points, fill=(13, 16, 20, 255), width=max(5, round(width * float(spec["width_fraction"]))))
        draw.line(points, fill=(58, 63, 70, 255), width=2)
    elif kind == "DARK_TOOL_POLYGON":
        overlay = _rotated_bar(size, angle, float(spec["width_fraction"]), (20, 23, 28, 255))
    elif kind == "ARTICULATED_HAND_PROXY":
        radius = width * 0.26
        draw.ellipse((center_x - radius, center_y - radius * 0.8, center_x + radius, center_y + radius * 0.8), fill=(188, 131, 102, 255))
        for index in range(4):
            finger_x = center_x - radius * 0.7 + index * radius * 0.45
            draw.rounded_rectangle((finger_x, center_y - radius * 1.35, finger_x + radius * 0.32, center_y), radius=4, fill=(205, 149, 117, 255))
    elif kind == "FOREIGN_OBJECT_POLYGON":
        radius = width * 0.34
        points = []
        for index in range(6):
            theta = math.radians(angle + index * 60)
            points.append((center_x + radius * math.cos(theta), center_y + radius * math.sin(theta)))
        draw.polygon(points, fill=(185, 67, 48, 255), outline=(64, 24, 20, 255))
    elif kind == "LOCALIZED_GLARE":
        glare = Image.new("L", size, 0)
        glare_draw = ImageDraw.Draw(glare)
        radius = width * 0.43
        glare_draw.ellipse((center_x - radius, center_y - radius * 0.65, center_x + radius, center_y + radius * 0.65), fill=int(spec["alpha"]))
        glare = glare.filter(ImageFilter.GaussianBlur(radius=width * 0.09))
        white = Image.new("RGB", size, (255, 255, 247))
        crop = Image.composite(white, crop, glare)
        return crop
    elif kind == "LOCAL_DEFOCUS_AND_COMPRESSION":
        crop = crop.filter(ImageFilter.GaussianBlur(radius=float(spec["blur_radius_px"])))
        buffer = io.BytesIO()
        crop.save(buffer, format="JPEG", quality=int(spec["jpeg_quality"]), optimize=False, progressive=False)
        return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")
    else:
        raise ValueError(f"unknown render kind: {kind}")
    return Image.alpha_composite(crop.convert("RGBA"), overlay).convert("RGB")


def _assert_zero_authority(payload: dict[str, Any]) -> None:
    if payload.get("hardware_writes") != 0 or payload.get("physical_movements") != 0 or payload.get("physical_authority") is not False:
        raise ValueError("artifact claims physical effects or authority")


def materialize(fixture_path: Path, source_manifest_path: Path, output_dir: Path) -> dict[str, Any]:
    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    _assert_zero_authority(fixture)
    if fixture.get("evaluation_group_present") is not False or fixture.get("training_started") is not False:
        raise ValueError("fixture is not an unopened pretraining freeze")
    source_manifest_path = source_manifest_path.resolve(strict=True)
    if sha256_bytes(source_manifest_path.read_bytes()) != fixture["source"]["manifest_file_sha256"]:
        raise ValueError("source manifest file hash mismatch")
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    output_dir.mkdir(parents=True)

    images: dict[str, Image.Image] = {}
    files: list[dict[str, Any]] = []
    try:
        for row in fixture["observations"]:
            base_name = row["base_image_path"]
            if base_name not in images:
                source_path = (source_manifest_path.parent / base_name).resolve(strict=True)
                if sha256_bytes(source_path.read_bytes()) != row["base_image_sha256"]:
                    raise ValueError(f"base image hash mismatch: {base_name}")
                images[base_name] = Image.open(source_path).convert("RGB")
            relative = Path(row["split"]) / f"{row['observation_id']}.png"
            destination = output_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            rendered = render_observation(row, images[base_name])
            rendered.save(destination, format="PNG", compress_level=9, optimize=False)
            payload = destination.read_bytes()
            files.append({
                "path": relative.as_posix(),
                "sha256": sha256_bytes(payload),
                "bytes": len(payload),
                "split": row["split"],
                "observation_id": row["observation_id"],
                "target_id": row["target_id"],
                "variant_id": row["variant_id"],
                "expected_decision": row["expected_decision"],
            })
    finally:
        for image in images.values():
            image.close()

    core = {
        "schema": DATASET_SCHEMA,
        "scope": "SYNTHETIC_RESIDUAL_PRETRAINING_NO_QUALIFICATION",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "source_manifest_file_sha256": fixture["source"]["manifest_file_sha256"],
        "files": files,
        "file_count": len(files),
        "inventory_sha256": sha256_bytes(canonical(files)),
        "evaluation_group_present": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    manifest = {**core, "dataset_sha256": sha256_bytes(canonical(core))}
    (output_dir / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return manifest


def verify_dataset(fixture_path: Path, dataset_dir: Path) -> dict[str, Any]:
    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    manifest_path = dataset_dir.resolve(strict=True) / "manifest.json"
    manifest = load_bound(manifest_path, DATASET_SCHEMA, "dataset_sha256")
    _assert_zero_authority(manifest)
    if manifest["fixture_file_sha256"] != sha256_bytes(fixture_path.read_bytes()) or manifest["fixture_bundle_sha256"] != fixture["bundle_sha256"]:
        raise ValueError("dataset fixture binding mismatch")
    expected_rows = {row["observation_id"]: row for row in fixture["observations"]}
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(expected_rows) or manifest.get("file_count") != len(entries):
        raise ValueError("dataset file count mismatch")
    if manifest.get("inventory_sha256") != sha256_bytes(canonical(entries)):
        raise ValueError("dataset inventory hash mismatch")
    declared_paths: set[str] = set()
    for entry in entries:
        identity = entry["observation_id"]
        if identity not in expected_rows:
            raise ValueError(f"unexpected observation: {identity}")
        row = expected_rows.pop(identity)
        for key in ("split", "target_id", "variant_id", "expected_decision"):
            if entry[key] != row[key]:
                raise ValueError(f"dataset metadata mismatch: {identity} / {key}")
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in declared_paths:
            raise ValueError("unsafe or duplicate dataset path")
        declared_paths.add(relative.as_posix())
        path = (dataset_dir / relative).resolve(strict=True)
        if dataset_dir.resolve() not in path.parents or path.is_symlink() or not path.is_file():
            raise ValueError("dataset path is not a contained regular file")
        payload = path.read_bytes()
        if len(payload) != entry["bytes"] or sha256_bytes(payload) != entry["sha256"]:
            raise ValueError(f"dataset file changed: {entry['path']}")
        with Image.open(path) as image:
            if image.size != tuple(row["crop_size_px"]) or image.mode != "RGB":
                raise ValueError(f"dataset image contract mismatch: {entry['path']}")
    if expected_rows:
        raise ValueError("dataset is missing observations")
    actual_paths = {
        path.relative_to(dataset_dir).as_posix()
        for path in dataset_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_paths != declared_paths:
        raise ValueError("dataset contains missing or extra files")
    return manifest


def _load_arrays(dataset_dir: Path, manifest: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, list[str], list[str], list[str]]:
    targets = sorted({entry["target_id"] for entry in manifest["files"]})
    target_index = {target: index for index, target in enumerate(targets)}
    rows = manifest["files"]
    arrays: list[np.ndarray] = []
    labels: list[float] = []
    splits: list[str] = []
    row_targets: list[str] = []
    identities: list[str] = []
    denominator = max(len(targets) - 1, 1)
    for entry in rows:
        with Image.open(dataset_dir / entry["path"]) as image:
            rgb = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        fourth = np.full((rgb.shape[0], rgb.shape[1], 1), target_index[entry["target_id"]] / denominator, dtype=np.float32)
        arrays.append(np.concatenate((rgb, fourth), axis=2).transpose(2, 0, 1))
        labels.append(1.0 if entry["expected_decision"] == "ABSTAIN" else 0.0)
        splits.append(entry["split"])
        row_targets.append(entry["target_id"])
        identities.append(entry["observation_id"])
    return np.stack(arrays), np.asarray(labels, dtype=np.float32), splits, row_targets, identities


def _rates(labels: np.ndarray, probabilities: np.ndarray, threshold: float) -> tuple[float, float, int, int]:
    predicted = probabilities >= threshold
    positives = labels == 1
    negatives = ~positives
    misses = int(np.sum(positives & ~predicted))
    false_stops = int(np.sum(negatives & predicted))
    return misses / int(np.sum(positives)), false_stops / int(np.sum(negatives)), misses, false_stops


def score_thresholds(labels: np.ndarray, probabilities: np.ndarray, targets: list[str], candidates: list[float], resamples: int, seed: int) -> list[dict[str, Any]]:
    unique_targets = sorted(set(targets))
    groups = [np.asarray([index for index, target in enumerate(targets) if target == identity]) for identity in unique_targets]
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(groups), size=(resamples, len(groups)))
    results = []
    for threshold in candidates:
        miss_rate, false_rate, misses, false_stops = _rates(labels, probabilities, threshold)
        per_group = []
        predicted = probabilities >= threshold
        for indices in groups:
            group_labels = labels[indices] == 1
            group_predictions = predicted[indices]
            per_group.append((
                int(np.sum(group_labels & ~group_predictions)), int(np.sum(group_labels)),
                int(np.sum(~group_labels & group_predictions)), int(np.sum(~group_labels)),
            ))
        values = np.asarray(per_group, dtype=np.int64)
        selected = values[samples].sum(axis=1)
        bootstrap_miss = selected[:, 0] / selected[:, 1]
        bootstrap_false = selected[:, 2] / selected[:, 3]
        miss_upper = float(np.quantile(bootstrap_miss, 0.95, method="higher"))
        false_upper = float(np.quantile(bootstrap_false, 0.95, method="higher"))
        results.append({
            "threshold": float(threshold),
            "missed_obstructions": misses,
            "obstruction_count": int(np.sum(labels == 1)),
            "missed_obstruction_rate": miss_rate,
            "missed_obstruction_cluster_upper": miss_upper,
            "visible_false_stops": false_stops,
            "visible_count": int(np.sum(labels == 0)),
            "visible_false_stop_rate": false_rate,
            "visible_false_stop_cluster_upper": false_upper,
            "gate_met": miss_rate <= 0.02 and false_rate <= 0.10 and miss_upper <= 0.02 and false_upper <= 0.10,
        })
    return results


def _write_model(path: Path, state: dict[str, Any], metadata: dict[str, Any]) -> None:
    with path.open("wb") as handle:
        handle.write(MODEL_MAGIC)
        meta = canonical(metadata)
        handle.write(struct.pack("<I", len(meta)))
        handle.write(meta)
        for name in sorted(state):
            array = state[name].detach().cpu().numpy().astype("<f4", copy=False)
            name_bytes = name.encode()
            handle.write(struct.pack("<I", len(name_bytes)))
            handle.write(name_bytes)
            handle.write(struct.pack("<I", array.ndim))
            handle.write(struct.pack("<" + "I" * array.ndim, *array.shape))
            handle.write(array.tobytes(order="C"))


def train(fixture_path: Path, dataset_dir: Path, output_dir: Path, retained_report: Path | None = None) -> dict[str, Any]:
    import torch

    fixture = load_bound(fixture_path.resolve(strict=True), FIXTURE_SCHEMA, "bundle_sha256")
    manifest = verify_dataset(fixture_path, dataset_dir)
    plan = fixture["training_plan"]
    gate = fixture["development_gate"]
    if output_dir.exists():
        raise FileExistsError(f"refusing existing output directory: {output_dir}")
    output_dir.mkdir(parents=True)
    x, y, splits, targets, identities = _load_arrays(dataset_dir, manifest)
    train_indices = np.asarray([index for index, split in enumerate(splits) if split == "training"])
    development_indices = np.asarray([index for index, split in enumerate(splits) if split == "development"])
    if any(split not in {"training", "development"} for split in splits):
        raise ValueError("evaluation or unknown split encountered")

    seed = int(plan["seed"])
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)

    channels = plan["convolution_channels"]
    model = torch.nn.Sequential(
        torch.nn.Conv2d(4, channels[0], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[0], channels[1], 3, padding=1), torch.nn.ReLU(), torch.nn.MaxPool2d(2),
        torch.nn.Conv2d(channels[1], channels[2], 3, padding=1), torch.nn.ReLU(),
        torch.nn.AdaptiveAvgPool2d((1, 1)), torch.nn.Flatten(), torch.nn.Linear(channels[2], 1),
    )
    train_x = torch.from_numpy(x[train_indices])
    train_y = torch.from_numpy(y[train_indices]).reshape(-1, 1)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(plan["learning_rate"]), weight_decay=float(plan["weight_decay"]))
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor([float(plan["positive_class_weight"])]))
    losses = []
    batch_size = int(plan["batch_size"])
    for epoch in range(int(plan["epochs"])):
        order = torch.randperm(len(train_x), generator=torch.Generator().manual_seed(seed + epoch))
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            optimizer.zero_grad()
            loss = loss_fn(model(train_x[batch]), train_y[batch])
            loss.backward()
            optimizer.step()
            total += float(loss.detach()) * len(batch)
        losses.append(total / len(order))

    model.eval()
    with torch.no_grad():
        probabilities = torch.sigmoid(model(torch.from_numpy(x[development_indices]))).reshape(-1).numpy()
    development_labels = y[development_indices]
    development_targets = [targets[index] for index in development_indices]
    measurements = score_thresholds(
        development_labels, probabilities, development_targets,
        [float(value) for value in plan["threshold_candidates"]],
        int(gate["target_cluster_bootstrap_resamples"]), int(gate["target_cluster_bootstrap_seed"]),
    )
    passing = [measurement for measurement in measurements if measurement["gate_met"]]
    selected = passing[0] if passing else None
    model_path = output_dir / "model.bin"
    metadata = {
        "algorithm": plan["algorithm"], "fixture_bundle_sha256": fixture["bundle_sha256"],
        "dataset_sha256": manifest["dataset_sha256"], "input_size_px": plan["input_size_px"],
        "input_channels": plan["input_channels"], "convolution_channels": channels,
        "target_id_encoding": "SORTED_CATALOG_INDEX_NORMALIZED_0_TO_1_CONSTANT_CHANNEL",
    }
    _write_model(model_path, model.state_dict(), metadata)
    core = {
        "schema": RESULT_SCHEMA,
        "scope": "SYNTHETIC_DEVELOPMENT_ONLY_NO_QUALIFICATION",
        "status": "PASSED_DEVELOPMENT_GATE" if selected else "FAILED_DEVELOPMENT_GATE",
        "fixture_file_sha256": sha256_bytes(fixture_path.read_bytes()),
        "fixture_bundle_sha256": fixture["bundle_sha256"],
        "dataset_manifest_file_sha256": sha256_bytes((dataset_dir / "manifest.json").read_bytes()),
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_inventory_sha256": manifest["inventory_sha256"],
        "model_sha256": sha256_bytes(model_path.read_bytes()),
        "model_bytes": model_path.stat().st_size,
        "training_plan": plan,
        "target_id_encoding": metadata["target_id_encoding"],
        "training_count": int(len(train_indices)),
        "development_count": int(len(development_indices)),
        "evaluation_count": 0,
        "epoch_losses": losses,
        "selected_threshold": None if selected is None else selected["threshold"],
        "selected_measurement": selected,
        "threshold_measurements": measurements,
        "development_probability_sha256": sha256_bytes(np.asarray(probabilities, dtype="<f4").tobytes()),
        "development_identity_sha256": sha256_bytes(canonical([identities[index] for index in development_indices])),
        "evaluation_opened": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "Training and development use two correlated synthetic practice views",
            "Procedural image-space obstructions are not physical obstruction evidence",
            "A development pass cannot qualify deployment or open physical authority",
            "No evaluation source was present or opened",
        ],
    }
    result = {**core, "result_sha256": sha256_bytes(canonical(core))}
    (output_dir / "scorecard.json").write_bytes(canonical(result) + b"\n")
    if retained_report is not None:
        retained_report.parent.mkdir(parents=True, exist_ok=True)
        retained_report.write_bytes(canonical(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    materialize_parser = subparsers.add_parser("materialize")
    materialize_parser.add_argument("--fixture", type=Path, required=True)
    materialize_parser.add_argument("--source-manifest", type=Path, required=True)
    materialize_parser.add_argument("--output-dir", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--fixture", type=Path, required=True)
    verify_parser.add_argument("--dataset-dir", type=Path, required=True)
    train_parser = subparsers.add_parser("train")
    train_parser.add_argument("--fixture", type=Path, required=True)
    train_parser.add_argument("--dataset-dir", type=Path, required=True)
    train_parser.add_argument("--output-dir", type=Path, required=True)
    train_parser.add_argument("--retained-report", type=Path)
    args = parser.parse_args()
    if args.command == "materialize":
        result = materialize(args.fixture, args.source_manifest, args.output_dir)
        summary = {"schema": result["schema"], "dataset_sha256": result["dataset_sha256"], "file_count": result["file_count"]}
    elif args.command == "verify":
        result = verify_dataset(args.fixture, args.dataset_dir)
        summary = {"schema": result["schema"], "dataset_sha256": result["dataset_sha256"], "file_count": result["file_count"]}
    else:
        result = train(args.fixture, args.dataset_dir, args.output_dir, args.retained_report)
        summary = {"schema": result["schema"], "status": result["status"], "result_sha256": result["result_sha256"], "selected_threshold": result["selected_threshold"]}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
