from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
BUILD_DIR = ROOT / "build"
REPORTS_DIR = BUILD_DIR / "reports"
ZENODO_DIR = BUILD_DIR / "zenodo-package"

INCOMPLETE_PARTICIPANTS = {"u_1", "u_2", "u_17"}
CORE_PARTICIPANTS = {*(f"u_{i}" for i in range(3, 17)), "u_18"}

GENERAL_GESTURES = [
    "g_flexext_fist",
    "g_flexext_thumb",
    "g_flexext_index",
    "g_flexext_middle",
    "g_flexext_ring",
    "g_flexext_pinky",
    "g_finger_tap_surface",
    "g_thumbs_up",
    "g_point_index",
    "g_ab_add_all",
    "g_ab_add_thumb_index",
    "g_ab_add_index_middle",
    "g_ab_add_middle_ring",
]

XRMI_GESTURES = [
    "g_tap_thumb",
    "g_tap_index",
    "g_tap_middle",
    "g_tap_ring",
    "g_tap_pinky",
    "g_pinched_tap_thumb_index",
    "g_pinched_tap_index_middle",
    "g_pinched_tap_middle_ring",
    "g_melody",
]

PUBLISHED_GESTURES = GENERAL_GESTURES + XRMI_GESTURES

RECORDING_RE = re.compile(
    r"^recording_(?P<speed>slow|medium|fast)_(?P<stamp>\d{2}_\d{2}_\d{4}_\d{2}_\d{2}_\d{2})\.csv$"
)

DIRECT_IDENTIFIER_FILENAMES = {
    "name.txt",
    "names.txt",
    "participant_names.txt",
    "reidentification_key.txt",
    "email.txt",
    "phone.txt",
}


@dataclass(frozen=True)
class Record:
    relative_path: str
    absolute_path: Path
    sha256: str
    size_bytes: int
    user_id: str
    session_id: str
    gesture_id: str
    speed: str
    row_count: int
    core_cohort: bool
    incomplete_participant: bool


def ensure_data_dir() -> None:
    if not DATA_DIR.exists():
        raise SystemExit(f"Missing data directory: {DATA_DIR}")


def participant_sort_key(name: str) -> int:
    return int(name.split("_", 1)[1])


def assert_clean_dataset() -> None:
    ensure_data_dir()
    hits = unexpected_gesture_paths()
    if hits:
        formatted = "\n".join(str(path) for path in hits)
        raise SystemExit(
            "Found unexpected gesture folders that must be removed before packaging:\n"
            f"{formatted}"
        )


def unexpected_gesture_paths() -> list[Path]:
    expected = set(PUBLISHED_GESTURES)
    hits: list[Path] = []
    for path in sorted(DATA_DIR.rglob("g_*")):
        if not path.is_dir():
            continue
        if path.name not in expected:
            hits.append(path)
    return hits


def iter_csv_files() -> list[Path]:
    assert_clean_dataset()
    return sorted(DATA_DIR.rglob("*.csv"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def parse_recording_path(path: Path) -> tuple[str, str, str, str]:
    rel = path.relative_to(DATA_DIR)
    if len(rel.parts) != 4:
        raise ValueError(f"Unexpected path shape: {path}")
    user_id, session_id, gesture_id, filename = rel.parts
    match = RECORDING_RE.match(filename)
    if not match:
        raise ValueError(f"Unexpected recording filename: {filename}")
    return user_id, session_id, gesture_id, match.group("speed")


def collect_records() -> list[Record]:
    records: list[Record] = []
    for path in iter_csv_files():
        user_id, session_id, gesture_id, speed = parse_recording_path(path)
        rel = path.relative_to(ROOT).as_posix()
        records.append(
            Record(
                relative_path=rel,
                absolute_path=path,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                user_id=user_id,
                session_id=session_id,
                gesture_id=gesture_id,
                speed=speed,
                row_count=count_rows(path),
                core_cohort=user_id in CORE_PARTICIPANTS,
                incomplete_participant=user_id in INCOMPLETE_PARTICIPANTS,
            )
        )
    return records


def group_counts(records: list[Record]) -> dict[tuple[str, str, str], int]:
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for record in records:
        counts[(record.user_id, record.session_id, record.gesture_id)] += 1
    return dict(counts)


def notes_for_record(record: Record, counts: dict[tuple[str, str, str], int]) -> list[str]:
    notes: list[str] = []
    if record.incomplete_participant:
        notes.append("participant_incomplete")
    count = counts[(record.user_id, record.session_id, record.gesture_id)]
    if count != 3:
        notes.append(f"expected_3_recordings_found_{count}")
    return notes


def manifest_rows(records: list[Record]) -> list[dict[str, str]]:
    counts = group_counts(records)
    rows: list[dict[str, str]] = []
    for record in records:
        notes = notes_for_record(record, counts)
        rows.append(
            {
                "relative_path": record.relative_path,
                "sha256": record.sha256,
                "size_bytes": str(record.size_bytes),
                "user_id": record.user_id,
                "session_id": record.session_id,
                "gesture_id": record.gesture_id,
                "speed": record.speed,
                "row_count": str(record.row_count),
                "core_cohort": str(record.core_cohort).lower(),
                "incomplete_participant": str(record.incomplete_participant).lower(),
                "anomaly_flag": str(bool(notes)).lower(),
                "notes": ";".join(notes),
            }
        )
    return rows


def write_manifest(output_path: Path, records: list[Record] | None = None) -> Path:
    rows = manifest_rows(records or collect_records())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "relative_path",
                "sha256",
                "size_bytes",
                "user_id",
                "session_id",
                "gesture_id",
                "speed",
                "row_count",
                "core_cohort",
                "incomplete_participant",
                "anomaly_flag",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def find_identifier_file_hits() -> list[str]:
    hits: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts or "build" in path.parts:
            continue
        if path.name.lower() in DIRECT_IDENTIFIER_FILENAMES:
            hits.append(path.relative_to(ROOT).as_posix())
    return hits


def qc_summary(records: list[Record] | None = None) -> dict:
    records = records or collect_records()
    counts = group_counts(records)
    per_user: dict[str, int] = defaultdict(int)
    per_session: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    anomalies: list[dict[str, object]] = []

    for record in records:
        per_user[record.user_id] += 1
        per_session[record.user_id][record.session_id] += 1

    for (user_id, session_id, gesture_id), count in sorted(counts.items()):
        if count != 3:
            anomalies.append(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "gesture_id": gesture_id,
                    "recording_count": count,
                    "core_cohort": user_id in CORE_PARTICIPANTS,
                    "incomplete_participant": user_id in INCOMPLETE_PARTICIPANTS,
                }
            )

    return {
        "published_gesture_count": len(PUBLISHED_GESTURES),
        "published_gestures": PUBLISHED_GESTURES,
        "participant_folder_count": len(
            {record.user_id for record in records}
        ),
        "total_csv_files": len(records),
        "core_cohort_participants": sorted(CORE_PARTICIPANTS, key=participant_sort_key),
        "core_cohort_csv_files": sum(1 for record in records if record.core_cohort),
        "incomplete_participants": sorted(INCOMPLETE_PARTICIPANTS, key=participant_sort_key),
        "per_user_csv_counts": {
            key: per_user[key] for key in sorted(per_user, key=participant_sort_key)
        },
        "per_user_session_csv_counts": {
            user_id: dict(sorted(sessions.items()))
            for user_id, sessions in sorted(
                per_session.items(), key=lambda item: participant_sort_key(item[0])
            )
        },
        "core_cohort_expected_csv_files": len(CORE_PARTICIPANTS) * 3 * 22 * 3,
        "core_cohort_net_difference": sum(1 for record in records if record.core_cohort)
        - (len(CORE_PARTICIPANTS) * 3 * 22 * 3),
        "anomalous_groups": anomalies,
        "unexpected_gesture_folder_hits": [
            path.relative_to(ROOT).as_posix() for path in unexpected_gesture_paths()
        ],
        "identifier_file_hits": find_identifier_file_hits(),
    }


def write_qc_report(output_prefix: Path, records: list[Record] | None = None) -> tuple[Path, Path]:
    summary = qc_summary(records)
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    md_path = output_prefix.with_suffix(".md")

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    lines = [
        "# QC Report",
        "",
        f"- Participant folders: {summary['participant_folder_count']}",
        f"- Total CSV files: {summary['total_csv_files']}",
        f"- Core cohort CSV files: {summary['core_cohort_csv_files']}",
        f"- Core cohort expected CSV files: {summary['core_cohort_expected_csv_files']}",
        f"- Core cohort net difference: {summary['core_cohort_net_difference']}",
        f"- Published gesture count: {summary['published_gesture_count']}",
        f"- Unexpected gesture folders: {len(summary['unexpected_gesture_folder_hits'])}",
        "",
        "## Incomplete Participants",
        "",
    ]

    for user_id in summary["incomplete_participants"]:
        lines.append(f"- {user_id}: {summary['per_user_csv_counts'][user_id]} CSV files")

    lines.extend(["", "## Anomalous Groups", ""])
    for item in summary["anomalous_groups"]:
        lines.append(
            f"- {item['user_id']}/{item['session_id']}/{item['gesture_id']}: "
            f"{item['recording_count']} recordings"
        )

    lines.extend(["", "## Unexpected Gesture Folders", ""])
    if summary["unexpected_gesture_folder_hits"]:
        for hit in summary["unexpected_gesture_folder_hits"]:
            lines.append(f"- {hit}")
    else:
        lines.append("- none")

    lines.extend(["", "## Identifier File Hits", ""])
    if summary["identifier_file_hits"]:
        for hit in summary["identifier_file_hits"]:
            lines.append(f"- {hit}")
    else:
        lines.append("- none")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def copy_dataset_docs(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in [
        "README.md",
        "CODEBOOK.md",
        "DATA_QUALITY.md",
        "LICENSE-data-CC-BY-4.0.txt",
    ]:
        shutil.copy2(ROOT / name, destination / name)


def build_data_zip(zip_path: Path) -> Path:
    assert_clean_dataset()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in iter_csv_files():
            archive.write(path, arcname=path.relative_to(ROOT).as_posix())
    return zip_path


def write_checksums(package_dir: Path, output_path: Path) -> Path:
    package_dir.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    for path in sorted(package_dir.rglob("*")):
        if not path.is_file():
            continue
        if path == output_path:
            continue
        rows.append(f"{sha256_file(path)}  {path.relative_to(package_dir).as_posix()}")
    output_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return output_path


def prepare_zenodo_package() -> dict[str, Path]:
    records = collect_records()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = write_manifest(BUILD_DIR / "manifest.csv", records)
    qc_json_path, qc_md_path = write_qc_report(REPORTS_DIR / "qc_report", records)

    if ZENODO_DIR.exists():
        shutil.rmtree(ZENODO_DIR)
    ZENODO_DIR.mkdir(parents=True, exist_ok=True)

    copy_dataset_docs(ZENODO_DIR)
    shutil.copy2(manifest_path, ZENODO_DIR / "manifest.csv")
    data_zip_path = build_data_zip(ZENODO_DIR / "semg-manus-dataset-v1.zip")
    checksums_path = write_checksums(ZENODO_DIR, ZENODO_DIR / "checksums.txt")

    return {
        "manifest": manifest_path,
        "qc_json": qc_json_path,
        "qc_md": qc_md_path,
        "data_zip": data_zip_path,
        "checksums": checksums_path,
        "package_dir": ZENODO_DIR,
    }
