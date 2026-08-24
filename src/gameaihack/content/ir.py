from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from jsonschema import Draft202012Validator

from gameaihack import __version__
from gameaihack.fingerprint import Fingerprint
from gameaihack.ingest import PackageInfo
from gameaihack.core.paths import load_yaml

SCHEMA_ID = "gameaihack.gameir.v1"

GAMEIR_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_ID,
    "type": "object",
    "required": [
        "$schema",
        "job_id",
        "package",
        "input_profile",
        "fingerprint",
        "radar",
        "claims",
        "unknowns",
    ],
    "properties": {
        "$schema": {"type": "string"},
        "job_id": {"type": "string", "minLength": 1},
        "package": {
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "version_name": {"type": ["string", "null"]},
                "version_code": {"type": ["integer", "null"]},
                "sha256": {"type": ["string", "null"]},
                "min_sdk": {"type": ["integer", "null"]},
                "orientation": {"type": ["string", "null"]},
            },
        },
        "input_profile": {
            "type": "object",
            "required": ["score", "warnings"],
            "properties": {
                "score": {"type": "integer", "minimum": 0, "maximum": 100},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "files": {"type": "array"},
            },
        },
        "fingerprint": {
            "type": "object",
            "required": ["engine"],
            "properties": {
                "engine": {
                    "type": "string",
                    "enum": [
                        "unity",
                        "unreal",
                        "cocos",
                        "godot",
                        "native",
                        "flutter",
                        "unknown",
                    ],
                }
            },
        },
        "radar": {
            "type": "array",
            "minItems": 20,
            "maxItems": 20,
            "items": {
                "type": "object",
                "required": ["dimension", "score", "max"],
                "properties": {
                    "dimension": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 5},
                    "max": {"type": "integer"},
                    "evidence_count": {"type": "integer"},
                    "blockers": {"type": "array", "items": {"type": "string"}},
                    "mode_needed_to_improve": {"type": ["string", "null"]},
                },
            },
        },
        "claims": {"type": "array"},
        "unknowns": {"type": "array"},
    },
    "additionalProperties": True,
}

_validator = Draft202012Validator(GAMEIR_SCHEMA)


def radar_phase0(fp: Fingerprint, pkg: PackageInfo) -> list[dict]:
    dims = load_yaml("radar_dimensions.yaml")["dimensions"]
    items = []
    for d in dims:
        score = int(d.get("default_phase0_score") or 0)
        blockers = []
        if d["id"] == "identity" and pkg.name == "unknown.pack":
            score = 1
            blockers.append("package_name_unknown")
        if d["id"] == "tech" and fp.engine == "unknown":
            score = 0
            blockers.append("engine_unknown")
        if score == 0:
            blockers.append("phase0_not_extracted")
        items.append(
            {
                "dimension": d["id"],
                "label": d.get("label") or d["id"],
                "score": score,
                "max": 5,
                "evidence_count": 0,
                "blockers": blockers,
                "mode_needed_to_improve": "standard",
            }
        )
    return items


def build_ir(
    *,
    job_id: str,
    pkg: PackageInfo,
    fp: Fingerprint,
    sha256: str,
    input_profile: dict,
) -> dict:
    radar = radar_phase0(fp, pkg)
    return {
        "$schema": SCHEMA_ID,
        "job_id": job_id,
        "package": {
            "name": pkg.name,
            "version_name": pkg.version_name,
            "version_code": pkg.version_code,
            "sha256": sha256,
            "min_sdk": pkg.min_sdk,
            "orientation": pkg.orientation,
        },
        "input_profile": input_profile,
        "fingerprint": fp.to_dict(),
        "genre_guess": {"id": None, "confidence": 0},
        "resources": [],
        "entity_templates": [],
        "tables": [],
        "levels": [],
        "ui": {"screens": [], "flows": []},
        "loc": {"languages": [], "samples": []},
        "verbs": [],
        "loops": {"session": [], "day": [], "meta": []},
        "economy": {"currencies": [], "sources": [], "sinks": [], "edges": []},
        "progression": {"nodes": [], "edges": []},
        "monetization": {"iap": [], "ads": [], "gacha": []},
        "feel": {"input": [], "camera": [], "juice": []},
        "formulas": [],
        "analytics_events": [],
        "network": {"client_authoritative": [], "server_authoritative": [], "apis": []},
        "claims": [],
        "radar": radar,
        "simulations": [],
        "unknowns": list(input_profile.get("warnings") or []),
        "coverage": {
            "resources": {"discovered": 0, "exported": 0, "encrypted": 0, "remote": 0},
            "code": {"java": "skipped", "csharp": "skipped", "lua": "skipped"},
            "levels": {"indexed": 0, "rebuild_l2_plus": 0},
            "tables": {"decoded": 0, "binary_unknown": 0},
            "design_claims": {"high": 0, "medium": 0, "low": 0, "hypothesis": 0},
            "radar": radar,
            "tool_version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def validate_ir(ir: dict) -> list[str]:
    errors = sorted(_validator.iter_errors(ir), key=lambda e: list(e.path))
    msgs = []
    for e in errors:
        loc = ".".join(str(p) for p in e.path) or "<root>"
        msgs.append(f"{loc}: {e.message}")
    dims = [x.get("dimension") for x in ir.get("radar") or []]
    want = [d["id"] for d in load_yaml("radar_dimensions.yaml")["dimensions"]]
    if dims != want:
        msgs.append(f"radar dimensions order/id mismatch: {dims} != {want}")
    for c in ir.get("claims") or []:
        if c.get("severity") == "confirmed" and not c.get("evidence"):
            msgs.append(f"claim {c.get('id')} confirmed without evidence")
    return msgs
