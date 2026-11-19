"""Versioned source regions for the vertical gamer composition."""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import re

from .common import load_session, read_json, resolve_media, write_json

PROFILE_NAME = "composition.json"
PRESET_ID = "gamer-stack-v1"
PRESET_PATH = Path(__file__).resolve().parents[1] / "layouts" / f"{PRESET_ID}.json"
RECT_FIELDS = ("x", "y", "width", "height")


def _region(name: str, rect: object) -> dict:
    if not isinstance(rect, dict) or rect.keys() != set(RECT_FIELDS):
        raise ValueError(f"A região {name} precisa de x, y, width e height normalizados.")
    if any(type(value) not in (int, float) or not 0 <= value <= 1 for value in rect.values()):
        raise ValueError(f"A região {name} precisa de números finitos entre 0 e 1.")
    x, y, width, height = (rect[field] for field in RECT_FIELDS)
    if width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError(f"A região {name} precisa ter área positiva e caber dentro do vídeo.")
    return {field: rect[field] for field in RECT_FIELDS}


def _source_size(video: object) -> dict:
    if not isinstance(video, dict):
        raise ValueError("Dimensões de vídeo inválidas em composition.json.")
    width, height = video.get("width"), video.get("height")
    if any(type(value) is not int or value < 1 for value in (width, height)):
        raise ValueError("Dimensões de vídeo inválidas em composition.json.")
    size = {"width": width, "height": height}
    sample_aspect = video.get("sample_aspect_ratio", "1:1")
    if not isinstance(sample_aspect, str) or not re.fullmatch(r"[1-9]\d*:[1-9]\d*", sample_aspect):
        raise ValueError("Proporção de pixel inválida em composition.json.")
    if sample_aspect != "1:1":
        size["sample_aspect_ratio"] = sample_aspect
    return size


def _aspect(size: dict) -> Fraction:
    horizontal, vertical = map(int, size.get("sample_aspect_ratio", "1:1").split(":"))
    return Fraction(size["width"] * horizontal, size["height"] * vertical)


def pixel_region(rect: dict, video: dict) -> tuple[int, int, int, int]:
    """Round each edge to its closest source pixel."""
    width, height = video["width"], video["height"]
    x, y = round(rect["x"] * width), round(rect["y"] * height)
    right = round((rect["x"] + rect["width"]) * width)
    bottom = round((rect["y"] + rect["height"]) * height)
    return x, y, right - x, bottom - y


def _profile(camera: object, gameplay: object, gameplay_fit: object, size: dict | None) -> dict:
    camera, gameplay = _region("camera", camera), _region("gameplay", gameplay)
    if camera == gameplay:
        raise ValueError("As regiões camera e gameplay precisam ser distintas.")
    if gameplay_fit not in ("contain", "cover"):
        raise ValueError("gameplay_fit precisa ser contain ou cover.")
    if size is not None:
        pixel_camera, pixel_gameplay = pixel_region(camera, size), pixel_region(gameplay, size)
        if min(*pixel_camera[2:], *pixel_gameplay[2:]) < 2:
            raise ValueError("Cada região precisa ter área de pelo menos 2 × 2 pixels no vídeo.")
        if pixel_camera == pixel_gameplay:
            raise ValueError("As regiões camera e gameplay precisam ocupar pixels distintos.")
    return {
        "version": 1, "preset": PRESET_ID, "camera": camera, "gameplay": gameplay,
        "gameplay_fit": gameplay_fit, "source_size": size,
    }


def configure_composition(
    session_dir: Path | str, camera: dict, gameplay: dict, gameplay_fit: str = "cover",
) -> dict:
    """Save normalized source regions for a media or live session."""
    directory = Path(session_dir).expanduser().resolve()
    session = load_session(directory)
    path = directory / PROFILE_NAME
    size = None
    if session["media"] is not None or session["kind"] != "live":
        # Local import avoids a cycle with the renderer, which reads this profile.
        from .media import probe

        media = resolve_media(directory)
        if media == path:
            raise ValueError("O caminho de composition.json coincide com o vídeo de origem.")
        size = _source_size(probe(media))
    profile = _profile(camera, gameplay, gameplay_fit, size)
    write_json(path, profile)
    return profile


def _capture_profile(session: dict) -> Path | None:
    if session["kind"] != "snapshot":
        return None
    metadata = session["metadata"]
    capture_path, capture_id = metadata.get("capture_path"), metadata.get("capture_id")
    if not isinstance(capture_path, str) or not capture_path or not isinstance(capture_id, str) or not capture_id:
        return None
    capture_directory = Path(capture_path)
    profile = capture_directory / PROFILE_NAME
    if not capture_directory.is_absolute() or not profile.is_file():
        return None
    try:
        capture = read_json(capture_directory / "capture.json")
    except (OSError, ValueError) as error:
        raise ValueError("Não foi possível verificar a identidade da captura. Configure composition no snapshot.") from error
    if not isinstance(capture, dict) or capture.get("capture_id") != capture_id:
        raise ValueError("A identidade da captura não corresponde ao snapshot. Configure composition no snapshot.")
    return profile


def load_composition(session_dir: Path | str, video_info: dict) -> dict:
    """Validate the profile for this source, with optional verified capture inheritance."""
    directory = Path(session_dir).expanduser().resolve()
    session = load_session(directory)
    path = directory / PROFILE_NAME
    can_leave_source_unspecified = session["kind"] == "live"
    if not path.exists():
        path = _capture_profile(session)
        can_leave_source_unspecified = path is not None
    if path is None or not path.is_file():
        raise ValueError("Montagem vertical exige composition.json. Configure camera e gameplay com ./run.sh composition.")
    profile = read_json(path)
    if (not isinstance(profile, dict) or type(profile.get("version")) is not int or profile["version"] != 1
            or profile.get("preset") != PRESET_ID or "source_size" not in profile):
        raise ValueError(f"composition.json inválido. Configure as regiões com o preset {PRESET_ID}.")

    current_size = _source_size(video_info)
    recorded_size = profile["source_size"]
    if recorded_size is None and can_leave_source_unspecified:
        recorded_size = current_size
    else:
        recorded_size = _source_size(recorded_size)
        if _aspect(recorded_size) != _aspect(current_size):
            raise ValueError("A proporção da fonte mudou. Reconfigure camera e gameplay com ./run.sh composition.")
    validated = _profile(profile.get("camera"), profile.get("gameplay"), profile.get("gameplay_fit"), current_size)
    validated["source_size"] = recorded_size
    return validated
