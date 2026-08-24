from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


KIND_DIR = {
    "texture": "textures",
    "sprite": "sprites",
    "atlas": "atlases",
    "audio": "audio",
    "mesh": "models",
    "anim": "animations",
    "font": "fonts",
    "shader": "shaders",
    "video": "video",
    "prefab": "prefabs",
    "script": "scripts",
    "config": "configs",
    "map": "maps",
    "other": "misc",
}


@dataclass
class ExtractItem:
    kind: str
    name: str
    original_path: str
    export_rel: str
    sha256: str
    bytes: int
    extractor: str
    meta: dict = field(default_factory=dict)

    def to_resource(self, idx: int) -> dict:
        return {
            "id": f"res_{idx:05d}",
            "kind": self.kind,
            "name": self.name,
            "export_path": self.export_rel,
            "original_path": self.original_path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "meta": self.meta,
            "referenced_by": [],
            "extractor": self.extractor,
        }


@dataclass
class ExtractReport:
    adapter: str
    items: list[ExtractItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    discovered: int = 0
    encrypted: int = 0
    extra: dict = field(default_factory=dict)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def kind_from_suffix(name: str) -> str | None:
    suf = Path(name).suffix.lower()
    return {
        ".png": "texture",
        ".jpg": "texture",
        ".jpeg": "texture",
        ".webp": "texture",
        ".tga": "texture",
        ".bmp": "texture",
        ".pvr": "texture",
        ".ccz": "texture",
        ".ktx": "texture",
        ".ogg": "audio",
        ".mp3": "audio",
        ".wav": "audio",
        ".m4a": "audio",
        ".mp4": "video",
        ".webm": "video",
        ".ttf": "font",
        ".otf": "font",
        ".fnt": "font",
        ".lua": "script",
        ".js": "script",
        ".ts": "script",
        ".cs": "script",
        ".gd": "script",
        ".tscn": "prefab",
        ".plist": "atlas",
        ".atlas": "atlas",
        ".tmx": "map",
        ".tmj": "map",
        ".json": "config",
        ".csv": "config",
        ".xml": "config",
        ".txt": "config",
        ".bytes": "other",
        ".shader": "shader",
        ".glb": "mesh",
        ".gltf": "mesh",
        ".fbx": "mesh",
        ".obj": "mesh",
        ".anim": "anim",
        ".spine": "anim",
        ".skel": "anim",
    }.get(suf)
