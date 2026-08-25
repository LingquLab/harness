#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# Licensed under the CANN Open Software License Agreement Version 2.0.
"""Inspect local CANN metadata and explicit NPU evidence without executing tools."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import stat
import sys
from typing import Any, Iterable


MAX_DIRECTORY_ENTRIES = 1024
MAX_COMPONENT_FILES = 256
MAX_PLATFORM_FILES = 256
MAX_METADATA_BYTES = 128 * 1024
MAX_CAPTURE_BYTES = 256 * 1024
MAX_PARSED_LINES = 4096
MAX_JSON_NESTING = 64

PLATFORM_CONFIG_DIRS = (
    "platform_config",
    "compiler/platform_config",
    "compiler/data/platform_config",
    "tools/platform_config",
    "aarch64-linux/data/platform_config",
    "x86_64-linux/data/platform_config",
)
RELEASE_CANDIDATES = (
    ("compiler/version.info", False),
    ("version.info", False),
    ("version.cfg", True),
)
SOC_FIELD_NAMES = {
    "soc",
    "socname",
    "socversion",
    "shortsocversion",
    "chipsoc",
    "chipname",
}
NPU_ARCH_FIELD_NAMES = {"npuarch"}
DRIVER_VERSION_FIELD_NAMES = {"driverversion"}
PLAIN_RELEASE_PATTERN = re.compile(
    r"^(?:CANN(?:CommunityEdition)?[ _-]+)?(?P<version>v?\d+(?:[._-][0-9A-Za-z]+)+)$",
    re.IGNORECASE,
)


class InspectionInputError(Exception):
    """Raised when an explicitly requested input cannot be inspected."""

    def __init__(self, message: str, *, code: str = "invalid_input") -> None:
        super().__init__(message)
        self.code = code


def json_nesting_exceeds_limit(text: str, limit: int) -> bool:
    depth = 0
    in_string = False
    escaped = False

    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > limit:
                return True
        elif character in "]}":
            depth -= 1

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect bounded CANN metadata and optional captured NPU evidence without "
            "network access, command execution, or dynamic-library loading."
        )
    )
    parser.add_argument("--toolkit-root", required=True, type=pathlib.Path)
    parser.add_argument(
        "--npu-capture",
        type=pathlib.Path,
        help="read a bounded JSON or key/value NPU capture instead of executing a device tool",
    )
    parser.add_argument(
        "--soc",
        help="explicit SoC identity; this is toolkit metadata evidence, not hardware detection",
    )
    parser.add_argument(
        "--build-target",
        help="explicit build target; this is never reported as detected hardware",
    )
    parser.add_argument("--json", action="store_true", help="emit stable JSON output")
    return parser.parse_args()


def diagnostic(
    diagnostics: list[dict[str, Any]],
    code: str,
    message: str,
    *,
    path: pathlib.Path | str | None = None,
) -> None:
    item: dict[str, Any] = {"code": code, "severity": "warning", "message": message}
    if path is not None:
        item["path"] = str(path)
    diagnostics.append(item)


def is_within(root: pathlib.Path, candidate: pathlib.Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_contained(
    root: pathlib.Path,
    candidate: pathlib.Path,
    diagnostics: list[dict[str, Any]],
) -> pathlib.Path | None:
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        diagnostic(
            diagnostics,
            "unreadable_path",
            f"metadata candidate cannot be resolved: {error}",
            path=candidate,
        )
        return None
    if not is_within(root, resolved):
        diagnostic(
            diagnostics,
            "path_outside_toolkit_root",
            "refusing to follow a metadata symlink outside the selected toolkit root",
            path=candidate,
        )
        return None
    return resolved


def read_bounded_text(
    path: pathlib.Path,
    byte_limit: int,
    diagnostics: list[dict[str, Any]],
) -> str | None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        diagnostic(diagnostics, "unreadable_file", str(error), path=path)
        return None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            diagnostic(
                diagnostics, "not_regular_file", "metadata is not a regular file", path=path
            )
            return None
        if metadata.st_size > byte_limit:
            diagnostic(
                diagnostics,
                "file_too_large",
                f"metadata exceeds the {byte_limit}-byte inspection limit",
                path=path,
            )
            return None

        chunks: list[bytes] = []
        remaining = byte_limit + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    except OSError as error:
        diagnostic(diagnostics, "unreadable_file", str(error), path=path)
        return None
    finally:
        os.close(descriptor)
    if len(data) > byte_limit:
        diagnostic(
            diagnostics,
            "file_too_large",
            f"metadata exceeds the {byte_limit}-byte inspection limit",
            path=path,
        )
        return None
    return data.decode("utf-8", errors="replace")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1].strip()
    return value


def normalized_key(key: str) -> str:
    return "".join(character for character in key.casefold() if character.isalnum())


def parse_key_values(text: str) -> list[tuple[str, str, int]]:
    fields: list[tuple[str, str, int]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if line_number > MAX_PARSED_LINES:
            break
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "[")):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else None
        if separator is None:
            continue
        key, value = line.split(separator, 1)
        key = key.strip()
        value = unquote(value)
        if key and value:
            fields.append((key, value, line_number))
    return fields


def field_claims(
    fields: Iterable[tuple[str, str, int]], names: set[str]
) -> list[tuple[str, str, int]]:
    return [field for field in fields if normalized_key(field[0]) in names]


def unique_values(claims: Iterable[dict[str, Any]]) -> list[str]:
    values_by_normalized_form: dict[str, str] = {}
    for claim in claims:
        value = str(claim["value"]).strip()
        if value:
            values_by_normalized_form.setdefault(value.casefold(), value)
    return sorted(values_by_normalized_form.values(), key=str.casefold)


def first_plain_release(text: str) -> tuple[str | None, int | None]:
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if line_number > MAX_PARSED_LINES:
            break
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        match = PLAIN_RELEASE_PATTERN.fullmatch(line)
        return (match.group("version"), line_number) if match else (None, line_number)
    return None, None


def scan_directory_names(
    directory: pathlib.Path,
    diagnostics: list[dict[str, Any]],
    *,
    code_prefix: str,
) -> list[str]:
    names: list[str] = []
    try:
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_DIRECTORY_ENTRIES:
                    diagnostic(
                        diagnostics,
                        f"{code_prefix}_directory_truncated",
                        f"directory scan stopped after {MAX_DIRECTORY_ENTRIES} entries",
                        path=directory,
                    )
                    break
                names.append(entry.name)
    except OSError as error:
        diagnostic(diagnostics, f"{code_prefix}_directory_unreadable", str(error), path=directory)
    return sorted(names, key=str.casefold)


def scan_components(
    root: pathlib.Path, diagnostics: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    share_info = root / "share" / "info"
    if not share_info.exists():
        return [], {}
    resolved_base = resolve_contained(root, share_info, diagnostics)
    if resolved_base is None or not resolved_base.is_dir():
        return [], {}

    components: list[dict[str, Any]] = []
    by_resolved_path: dict[str, dict[str, Any]] = {}
    candidate_count = 0
    for name in scan_directory_names(resolved_base, diagnostics, code_prefix="component"):
        candidate = share_info / name / "version.info"
        if not candidate.exists() and not candidate.is_symlink():
            continue
        if candidate_count >= MAX_COMPONENT_FILES:
            diagnostic(
                diagnostics,
                "component_scan_truncated",
                f"component metadata scan stopped after {MAX_COMPONENT_FILES} files",
                path=share_info,
            )
            break
        candidate_count += 1
        resolved = resolve_contained(root, candidate, diagnostics)
        if resolved is None:
            continue
        text = read_bounded_text(resolved, MAX_METADATA_BYTES, diagnostics)
        if text is None:
            continue
        fields = parse_key_values(text)
        version_fields = field_claims(fields, {"version"})
        versions = sorted({value for _, value, _ in version_fields}, key=str.casefold)
        version = versions[0] if len(versions) == 1 else None
        if len(versions) > 1:
            diagnostic(
                diagnostics,
                "component_version_conflict",
                f"component metadata contains conflicting Version fields: {', '.join(versions)}",
                path=candidate,
            )
        elif not versions:
            diagnostic(
                diagnostics,
                "component_version_missing",
                "component metadata has no Version field",
                path=candidate,
            )

        resolved_key = str(resolved)
        if resolved_key in by_resolved_path:
            existing = by_resolved_path[resolved_key]
            existing["aliases"].append(str(candidate))
            existing["component_id_aliases"].append(name)
            diagnostic(
                diagnostics,
                "component_metadata_alias",
                f"component {name} resolves to metadata already used by {existing['component_id']}",
                path=candidate,
            )
            continue

        version_provenance = None
        if len(versions) == 1 and version_fields:
            key, _, line = version_fields[0]
            version_provenance = {
                "source_kind": "component_metadata",
                "path": str(candidate),
                "resolved_path": resolved_key,
                "field": key,
                "line": line,
            }
        requirement_claims: list[dict[str, Any]] = []
        claims_by_key: dict[str, list[dict[str, Any]]] = {}
        for key, value, line in fields:
            if not key.casefold().startswith("required_package_"):
                continue
            claim = {
                "field": key,
                "value": value,
                "provenance": {
                    "source_kind": "component_metadata",
                    "path": str(candidate),
                    "resolved_path": resolved_key,
                    "field": key,
                    "line": line,
                },
            }
            requirement_claims.append(claim)
            claims_by_key.setdefault(key.casefold(), []).append(claim)

        requirements: dict[str, str] = {}
        requirement_conflicts: dict[str, list[str]] = {}
        for key_claims in claims_by_key.values():
            display_key = str(key_claims[0]["field"])
            values = unique_values(key_claims)
            if len(values) == 1:
                requirements[display_key] = values[0]
                continue
            requirement_conflicts[display_key] = values
            diagnostic(
                diagnostics,
                "component_requirement_conflict",
                f"component requirement {display_key} has conflicting values: "
                + ", ".join(values),
                path=candidate,
            )
        component = {
            "component_id": name,
            "component_id_aliases": [],
            "version": version,
            "version_provenance": version_provenance,
            "metadata_path": str(candidate),
            "resolved_path": resolved_key,
            "aliases": [],
            "requirements": dict(sorted(requirements.items(), key=lambda item: item[0].casefold())),
            "requirement_claims": requirement_claims,
            "requirement_conflicts": dict(
                sorted(requirement_conflicts.items(), key=lambda item: item[0].casefold())
            ),
            "version_text_relation": "unknown",
        }
        components.append(component)
        by_resolved_path[resolved_key] = component

    components.sort(key=lambda item: item["component_id"].casefold())
    return components, by_resolved_path


def scan_release_claims(
    root: pathlib.Path,
    diagnostics: list[dict[str, Any]],
    components_by_path: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None, str]:
    claims: list[dict[str, Any]] = []
    for relative_path, allow_plain_text in RELEASE_CANDIDATES:
        candidate = root / relative_path
        if not candidate.exists() and not candidate.is_symlink():
            continue
        resolved = resolve_contained(root, candidate, diagnostics)
        if resolved is None:
            continue
        text = read_bounded_text(resolved, MAX_METADATA_BYTES, diagnostics)
        if text is None:
            continue
        fields = parse_key_values(text)
        versions = field_claims(fields, {"version"})
        version_values = sorted({value for _, value, _ in versions}, key=str.casefold)
        if len(version_values) == 1:
            field, _, line = versions[0]
            value = version_values[0]
        elif not version_values and allow_plain_text:
            value, line = first_plain_release(text)
            if line is None:
                continue
            if value is None:
                diagnostic(
                    diagnostics,
                    "toolkit_release_plain_text_invalid",
                    "first non-comment line is not a release-shaped version token",
                    path=candidate,
                )
                continue
            field = "<first-nonempty-line>"
        elif len(version_values) > 1:
            diagnostic(
                diagnostics,
                "toolkit_release_file_conflict",
                "toolkit metadata contains more than one distinct Version field",
                path=candidate,
            )
            for field, value, line in versions:
                claims.append(
                    {
                        "value": value,
                        "provenance": {
                            "source_kind": "toolkit_metadata",
                            "path": str(candidate),
                            "resolved_path": str(resolved),
                            "field": field,
                            "line": line,
                        },
                    }
                )
        else:
            continue
        if len(version_values) <= 1:
            claims.append(
                {
                    "value": value,
                    "provenance": {
                        "source_kind": "toolkit_metadata",
                        "path": str(candidate),
                        "resolved_path": str(resolved),
                        "field": field,
                        "line": line,
                    },
                }
            )
        component = components_by_path.get(str(resolved))
        if component is not None and str(candidate) != component["metadata_path"]:
            component["aliases"].append(str(candidate))

    values = unique_values(claims)
    if len(values) == 1:
        return claims, values[0], "resolved"
    if len(values) > 1:
        diagnostic(
            diagnostics,
            "toolkit_release_conflict",
            "toolkit release metadata disagrees: " + ", ".join(values),
            path=root,
        )
        return claims, None, "conflict"
    return claims, None, "unknown"


def scan_platform_configs(
    root: pathlib.Path, diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    candidates: list[pathlib.Path] = []
    seen_candidates: set[str] = set()
    for relative_directory in PLATFORM_CONFIG_DIRS:
        directory = root / relative_directory
        if not directory.exists():
            continue
        resolved_directory = resolve_contained(root, directory, diagnostics)
        if resolved_directory is None or not resolved_directory.is_dir():
            continue
        for name in scan_directory_names(
            resolved_directory, diagnostics, code_prefix="platform_config"
        ):
            if not name.casefold().endswith(".ini"):
                continue
            candidate = directory / name
            candidate_key = str(candidate)
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            if len(candidates) >= MAX_PLATFORM_FILES:
                diagnostic(
                    diagnostics,
                    "platform_config_scan_truncated",
                    f"platform config scan stopped after {MAX_PLATFORM_FILES} files",
                    path=directory,
                )
                break
            candidates.append(candidate)
        if len(candidates) >= MAX_PLATFORM_FILES:
            break

    configs: list[dict[str, Any]] = []
    seen_resolved: set[str] = set()
    for candidate in sorted(candidates, key=lambda path: str(path).casefold()):
        resolved = resolve_contained(root, candidate, diagnostics)
        if resolved is None:
            continue
        resolved_key = str(resolved)
        if resolved_key in seen_resolved:
            continue
        seen_resolved.add(resolved_key)
        text = read_bounded_text(resolved, MAX_METADATA_BYTES, diagnostics)
        if text is None:
            continue
        fields = parse_key_values(text)
        identifiers: list[dict[str, Any]] = [
            {
                "value": candidate.stem,
                "provenance": {
                    "source_kind": "platform_config_filename",
                    "path": str(candidate),
                    "field": "<filename-stem>",
                },
            }
        ]
        for field, value, line in field_claims(fields, SOC_FIELD_NAMES):
            identifiers.append(
                {
                    "value": value,
                    "provenance": {
                        "source_kind": "platform_config_field",
                        "path": str(candidate),
                        "resolved_path": resolved_key,
                        "field": field,
                        "line": line,
                    },
                }
            )
        deduplicated_identifiers: list[dict[str, Any]] = []
        seen_identifiers: set[str] = set()
        for identifier in identifiers:
            normalized = identifier["value"].strip().casefold()
            if normalized and normalized not in seen_identifiers:
                deduplicated_identifiers.append(identifier)
                seen_identifiers.add(normalized)

        arch_fields = field_claims(fields, NPU_ARCH_FIELD_NAMES)
        arch_claims_by_value: dict[str, tuple[str, str, int]] = {}
        for field, value, line in arch_fields:
            arch_claims_by_value.setdefault(value.casefold(), (field, value, line))
        arch_values = sorted(arch_claims_by_value.values(), key=lambda item: item[1].casefold())
        arch_evidence = None
        if len(arch_values) == 1:
            field, value, line = arch_values[0]
            arch_evidence = {
                "value": value,
                "provenance": {
                    "source_kind": "platform_config_field",
                    "path": str(candidate),
                    "resolved_path": resolved_key,
                    "field": field,
                    "line": line,
                },
            }
        elif len(arch_values) > 1:
            diagnostic(
                diagnostics,
                "platform_npu_arch_conflict",
                "platform config contains conflicting NpuArch fields",
                path=candidate,
            )
        configs.append(
            {
                "path": str(candidate),
                "resolved_path": resolved_key,
                "soc_identifiers": deduplicated_identifiers,
                "npu_arch": arch_evidence,
            }
        )
    return configs


def capture_claim(
    value: Any,
    path: pathlib.Path,
    locator: str,
    claim_kind: str,
) -> dict[str, Any] | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    rendered = str(value).strip()
    if not rendered:
        return None
    return {
        "value": rendered,
        "provenance": {
            "source_kind": claim_kind,
            "path": str(path),
            "field": locator,
        },
    }


def parse_json_capture(
    payload: Any, path: pathlib.Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    soc_claims: list[dict[str, Any]] = []
    driver_claims: list[dict[str, Any]] = []
    has_invalid_identity_field = False
    if not isinstance(payload, dict):
        return soc_claims, driver_claims, has_invalid_identity_field

    def append_claim(
        value: Any, locator: str, target: list[dict[str, Any]]
    ) -> None:
        nonlocal has_invalid_identity_field
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            has_invalid_identity_field = True
            return
        claim = capture_claim(value, path, locator, "npu_capture_json")
        if claim is not None:
            target.append(claim)

    for key in ("soc", "soc_name", "soc_version"):
        if key in payload:
            append_claim(payload[key], f"$.{key}", soc_claims)
    if "driver_version" in payload:
        append_claim(payload["driver_version"], "$.driver_version", driver_claims)

    devices = payload.get("devices", [])
    if isinstance(devices, list):
        for index, device in enumerate(devices):
            if not isinstance(device, dict):
                continue
            for key in ("soc", "soc_name", "soc_version"):
                if key in device:
                    append_claim(device[key], f"$.devices[{index}].{key}", soc_claims)
            if "driver_version" in device:
                append_claim(
                    device["driver_version"],
                    f"$.devices[{index}].driver_version",
                    driver_claims,
                )
    return soc_claims, driver_claims, has_invalid_identity_field


def parse_npu_capture(
    capture_path: pathlib.Path | None, diagnostics: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    if capture_path is None:
        return [], [], None
    try:
        resolved = capture_path.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise InspectionInputError(
            f"NPU capture cannot be resolved: {error}", code="invalid_npu_capture"
        ) from error
    text = read_bounded_text(resolved, MAX_CAPTURE_BYTES, diagnostics)
    if text is None:
        reason = diagnostics[-1]["code"] if diagnostics else "unreadable_file"
        raise InspectionInputError(
            f"NPU capture could not be inspected within safety limits: {reason}",
            code="invalid_npu_capture",
        )

    soc_claims: list[dict[str, Any]] = []
    driver_claims: list[dict[str, Any]] = []
    json_candidate = text.lstrip("\ufeff \t\r\n")
    looks_like_json = json_candidate.startswith(("{", "["))
    if looks_like_json and json_nesting_exceeds_limit(
        json_candidate, MAX_JSON_NESTING
    ):
        raise InspectionInputError(
            f"NPU capture exceeds the JSON nesting limit of {MAX_JSON_NESTING}",
            code="invalid_npu_capture",
        )
    json_parsed = True
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        json_parsed = False
        payload = None
    except (MemoryError, RecursionError) as error:
        raise InspectionInputError(
            "NPU capture exceeds JSON parser resource limits", code="invalid_npu_capture"
        ) from error
    if json_parsed:
        capture_format = "json"
        if isinstance(payload, dict):
            soc_claims, driver_claims, has_invalid_identity_field = parse_json_capture(
                payload, capture_path
            )
            if has_invalid_identity_field:
                soc_claims = []
                driver_claims = []
                capture_status = "unrecognized"
                diagnostic(
                    diagnostics,
                    "capture_schema_unrecognized",
                    "JSON NPU capture has an invalid named SoC or driver field; "
                    "no hardware claim was inferred",
                    path=capture_path,
                )
            else:
                capture_status = "recognized" if soc_claims or driver_claims else "recognized_no_claims"
        else:
            capture_status = "unrecognized"
            diagnostic(
                diagnostics,
                "capture_schema_unrecognized",
                "JSON NPU capture root is not an object; no hardware claim was inferred",
                path=capture_path,
            )
    elif looks_like_json:
        capture_format = "json"
        capture_status = "unrecognized"
        diagnostic(
            diagnostics,
            "capture_json_invalid",
            "JSON-looking NPU capture is malformed; no hardware claim was inferred",
            path=capture_path,
        )
    else:
        capture_format = "key_value_text"
        fields = parse_key_values(text)
        for field, value, line in fields:
            normalized = normalized_key(field)
            target = None
            if normalized in SOC_FIELD_NAMES:
                target = soc_claims
            elif normalized in DRIVER_VERSION_FIELD_NAMES:
                target = driver_claims
            if target is None:
                continue
            target.append(
                {
                    "value": value,
                    "provenance": {
                        "source_kind": "npu_capture_text",
                        "path": str(capture_path),
                        "resolved_path": str(resolved),
                        "field": field,
                        "line": line,
                    },
                }
            )
        capture_status = "recognized" if soc_claims or driver_claims else "unrecognized"
        if capture_status == "unrecognized":
            diagnostic(
                diagnostics,
                "capture_schema_unrecognized",
                "NPU capture has no recognized named SoC or driver fields",
                path=capture_path,
            )

    evidence = {
        "path": str(capture_path),
        "resolved_path": str(resolved),
        "format": capture_format,
        "status": capture_status,
        "bounded_bytes": len(text.encode("utf-8")),
    }
    return soc_claims, driver_claims, evidence


def resolve_claims(
    claims: list[dict[str, Any]],
    diagnostics: list[dict[str, Any]],
    *,
    conflict_code: str,
    conflict_label: str,
) -> tuple[str | None, str]:
    values = unique_values(claims)
    if len(values) == 1:
        return values[0], "resolved"
    if len(values) > 1:
        diagnostic(
            diagnostics,
            conflict_code,
            f"{conflict_label} claims disagree: {', '.join(values)}",
        )
        return None, "conflict"
    return None, "unknown"


def resolve_npu_arch(
    platform_configs: list[dict[str, Any]],
    runtime_soc_claims: list[dict[str, Any]],
    requested_soc: str | None,
    build_target: str | None,
    diagnostics: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    runtime_soc, runtime_status = resolve_claims(
        runtime_soc_claims,
        diagnostics,
        conflict_code="runtime_soc_conflict",
        conflict_label="runtime SoC",
    )
    requested = requested_soc.strip() if requested_soc else None
    build = build_target.strip() if build_target else None
    if requested == "":
        requested = None
    if build == "":
        build = None

    selected_soc = None
    selected_source = None
    if runtime_status == "resolved":
        selected_soc = runtime_soc
        selected_source = "runtime_capture"
        if requested is not None and requested.casefold() != runtime_soc.casefold():
            diagnostic(
                diagnostics,
                "requested_soc_differs_from_runtime",
                f"requested SoC {requested} differs from runtime evidence {runtime_soc}",
            )
    elif runtime_status == "unknown" and requested is not None:
        selected_soc = requested
        selected_source = "user_supplied"

    matches: list[dict[str, Any]] = []
    if selected_soc is not None:
        wanted = selected_soc.casefold()
        for config in platform_configs:
            matching_identifiers = [
                identifier
                for identifier in config["soc_identifiers"]
                if identifier["value"].strip().casefold() == wanted
            ]
            if matching_identifiers:
                matches.append({"config": config, "identifiers": matching_identifiers})

    match_status = "not_attempted" if selected_soc is None else "none"
    value = None
    state = "unknown"
    evidence: list[dict[str, Any]] = []
    if selected_source == "runtime_capture" and runtime_soc_claims:
        evidence.extend(runtime_soc_claims)
    elif selected_source == "user_supplied" and selected_soc is not None:
        evidence.append(
            {
                "value": selected_soc,
                "provenance": {"source_kind": "user_supplied_soc", "argument": "--soc"},
            }
        )

    if len(matches) == 1:
        match_status = "exact"
        matched_config = matches[0]["config"]
        matched_identifier_evidence = matches[0]["identifiers"]
        evidence.extend(matched_identifier_evidence)
        arch_evidence = matched_config["npu_arch"]
        if arch_evidence is not None:
            value = arch_evidence["value"]
            evidence.append(arch_evidence)
            state = (
                "runtime_soc_correlated"
                if selected_source == "runtime_capture"
                else "toolkit_metadata_only"
            )
        else:
            diagnostic(
                diagnostics,
                "matched_platform_has_no_npu_arch",
                "the exactly matched platform config has no unambiguous NpuArch field",
                path=matched_config["path"],
            )
    elif len(matches) > 1:
        match_status = "ambiguous"
        diagnostic(
            diagnostics,
            "ambiguous_platform_match",
            "more than one platform config exactly matches the selected SoC; no NpuArch was chosen",
        )

    build_evidence = None
    if build is not None:
        build_evidence = {
            "value": build,
            "provenance": {"source_kind": "user_supplied_build_target", "argument": "--build-target"},
        }
        if value is not None and build.casefold() != value.casefold():
            diagnostic(
                diagnostics,
                "build_target_differs_from_resolved_npu_arch",
                f"build target {build} differs from resolved NpuArch {value}",
            )
        if value is None:
            value = build
            state = "build_target_only"
            evidence.append(build_evidence)

    soc_result = {
        "runtime_claims": runtime_soc_claims,
        "runtime_status": runtime_status,
        "runtime_value": runtime_soc,
        "requested_value": requested,
        "selected_for_resolution": selected_soc,
        "selected_source": selected_source,
    }
    arch_result = {
        "value": value,
        "state": state,
        "match_status": match_status,
        "matched_platform_paths": [match["config"]["path"] for match in matches],
        "matched_soc_identifier_evidence": [
            identifier for match in matches for identifier in match["identifiers"]
        ],
        "evidence": evidence,
        "build_target": build_evidence,
    }
    return soc_result, arch_result


def inspect(args: argparse.Namespace) -> dict[str, Any]:
    try:
        root = args.toolkit_root.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise InspectionInputError(f"toolkit root cannot be resolved: {error}") from error
    if not root.is_dir():
        raise InspectionInputError(f"toolkit root is not a directory: {args.toolkit_root}")

    diagnostics: list[dict[str, Any]] = []
    components, components_by_path = scan_components(root, diagnostics)
    release_claims, resolved_release, release_status = scan_release_claims(
        root, diagnostics, components_by_path
    )
    for component in components:
        component["aliases"].sort(key=str.casefold)
        component["component_id_aliases"].sort(key=str.casefold)
        if component["version"] is not None and resolved_release is not None:
            component["version_text_relation"] = (
                "equal"
                if component["version"].casefold() == resolved_release.casefold()
                else "different"
            )

    platform_configs = scan_platform_configs(root, diagnostics)
    runtime_soc_claims, driver_claims, capture_evidence = parse_npu_capture(
        args.npu_capture, diagnostics
    )
    driver_version, driver_status = resolve_claims(
        driver_claims,
        diagnostics,
        conflict_code="driver_version_conflict",
        conflict_label="driver version",
    )
    soc_result, npu_arch_result = resolve_npu_arch(
        platform_configs,
        runtime_soc_claims,
        args.soc,
        args.build_target,
        diagnostics,
    )
    diagnostics.sort(key=lambda item: (item["code"], item.get("path", ""), item["message"]))
    return {
        "schema_version": 1,
        "success": True,
        "toolkit": {
            "input_root": str(args.toolkit_root),
            "resolved_root": str(root),
            "release_claims": release_claims,
            "resolved_release": resolved_release,
            "release_status": release_status,
        },
        "components": components,
        "driver": {
            "version_claims": driver_claims,
            "resolved_version": driver_version,
            "status": driver_status,
        },
        "npu_capture": capture_evidence,
        "soc": soc_result,
        "npu_arch": npu_arch_result,
        "platform_configs": platform_configs,
        "diagnostics": diagnostics,
        "note": (
            "Version equality and local metadata are evidence only; this report does not prove "
            "component, driver, firmware, OS, or SoC compatibility."
        ),
    }


def display_text(value: Any) -> str:
    escaped: list[str] = []
    for character in str(value):
        if character == "\n":
            escaped.append(r"\n")
        elif character == "\r":
            escaped.append(r"\r")
        elif character == "\t":
            escaped.append(r"\t")
        elif character.isprintable():
            escaped.append(character)
        elif ord(character) <= 0xFF:
            escaped.append(f"\\x{ord(character):02x}")
        else:
            escaped.append(f"\\u{ord(character):04x}")
    return "".join(escaped)


def print_text(result: dict[str, Any]) -> None:
    toolkit = result["toolkit"]
    print("CANN state inspection")
    print("---------------------")
    print(f"toolkit root: {display_text(toolkit['resolved_root'])}")
    print(
        "toolkit release: "
        f"{display_text(toolkit['resolved_release'] or '<unknown>')} "
        f"({display_text(toolkit['release_status'])})"
    )
    print(f"components: {len(result['components'])}")
    for component in result["components"]:
        print(
            f"  {display_text(component['component_id'])}: "
            f"{display_text(component['version'] or '<unknown>')} "
            f"[version-text={display_text(component['version_text_relation'])}] "
            f"(source: {display_text(component['metadata_path'])})"
        )
    print(
        f"driver: {display_text(result['driver']['resolved_version'] or '<unknown>')} "
        f"({display_text(result['driver']['status'])})"
    )
    print(
        f"SoC: {display_text(result['soc']['selected_for_resolution'] or '<unknown>')}; "
        f"NpuArch: {display_text(result['npu_arch']['value'] or '<unknown>')} "
        f"({display_text(result['npu_arch']['state'])}, "
        f"{display_text(result['npu_arch']['match_status'])})"
    )
    for item in result["diagnostics"]:
        location = f" ({display_text(item['path'])})" if "path" in item else ""
        print(
            f"[warn] {display_text(item['code'])}: {display_text(item['message'])}{location}"
        )
    print(f"note: {result['note']}")


def error_result(message: str, *, code: str = "invalid_input") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "success": False,
        "error": {"code": code, "message": message},
    }


def main() -> int:
    args = parse_args()
    try:
        result = inspect(args)
    except InspectionInputError as error:
        result = error_result(str(error), code=error.code)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"error: {display_text(error)}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
