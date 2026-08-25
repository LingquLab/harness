#!/usr/bin/env python3
"""Offline regression tests for the bounded CANN state inspector."""

from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "plugins/ascendc-development/skills/ascendc-env-check/scripts/inspect_cann_state.py"
)
JSON_NESTING_LIMIT = 64


def write_version(path: pathlib.Path, version: str, extra: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"Version={version}\n{extra}", encoding="utf-8")


class CannStateInspectorTest(unittest.TestCase):
    def run_inspector(
        self, toolkit_root: pathlib.Path, *arguments: str, timeout: float | None = None
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        completed = subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--toolkit-root",
                str(toolkit_root),
                *arguments,
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        payload = json.loads(completed.stdout)
        return completed, payload

    def test_reports_component_driver_soc_and_arch_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            write_version(root / "compiler/version.info", "9.1.0")
            write_version(
                root / "share/info/asc-devkit/version.info",
                "9.1.0",
                'required_package_runtime_version="9.1.0"\n',
            )
            write_version(root / "share/info/asc-tools/version.info", "9.1.0")
            write_version(root / "share/info/ops-nn/version.info", "9.1.0")
            platform = root / "compiler/data/platform_config/Ascend910B3.ini"
            platform.parent.mkdir(parents=True)
            platform.write_text(
                "[Platform]\nShort_SoC_version=Ascend910B3\nNpuArch=dav-c220-cube\n",
                encoding="utf-8",
            )
            capture = pathlib.Path(temporary) / "npu.txt"
            capture.write_text(
                "SoC Name: Ascend910B3\nDriver Version: 25.5.0\n", encoding="utf-8"
            )

            completed, payload = self.run_inspector(
                root, "--npu-capture", str(capture), "--build-target", "dav-c220-cube"
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["toolkit"]["resolved_release"], "9.1.0")
        self.assertEqual(
            [component["component_id"] for component in payload["components"]],
            ["asc-devkit", "asc-tools", "ops-nn"],
        )
        devkit = payload["components"][0]
        self.assertEqual(devkit["requirements"], {"required_package_runtime_version": "9.1.0"})
        self.assertEqual(devkit["requirement_conflicts"], {})
        self.assertEqual(len(devkit["requirement_claims"]), 1)
        self.assertEqual(devkit["version_provenance"]["source_kind"], "component_metadata")
        self.assertEqual(payload["driver"]["resolved_version"], "25.5.0")
        self.assertEqual(payload["soc"]["runtime_value"], "Ascend910B3")
        self.assertEqual(payload["npu_arch"]["value"], "dav-c220-cube")
        self.assertEqual(payload["npu_arch"]["state"], "runtime_soc_correlated")
        self.assertEqual(payload["npu_arch"]["match_status"], "exact")
        self.assertEqual(
            payload["npu_arch"]["matched_soc_identifier_evidence"][0]["value"],
            "Ascend910B3",
        )
        self.assertEqual(
            payload["npu_arch"]["evidence"][-1]["provenance"]["source_kind"],
            "platform_config_field",
        )

    def test_release_conflict_is_reported_without_compatibility_guess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            write_version(root / "compiler/version.info", "9.1.0")
            write_version(root / "version.info", "8.0.RC3")
            write_version(root / "share/info/runtime/version.info", "9.1.0")

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNone(payload["toolkit"]["resolved_release"])
        self.assertEqual(payload["toolkit"]["release_status"], "conflict")
        self.assertEqual(payload["components"][0]["version_text_relation"], "unknown")
        self.assertIn(
            "toolkit_release_conflict",
            {item["code"] for item in payload["diagnostics"]},
        )
        self.assertIn("does not prove", payload["note"])

    def test_conflict_inside_one_release_file_cannot_be_hidden_by_another_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            write_version(root / "compiler/version.info", "9.1.0", "Version=8.0.RC3\n")
            write_version(root / "version.info", "9.1.0")

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNone(payload["toolkit"]["resolved_release"])
        self.assertEqual(payload["toolkit"]["release_status"], "conflict")
        self.assertEqual(
            {claim["value"] for claim in payload["toolkit"]["release_claims"]},
            {"8.0.RC3", "9.1.0"},
        )
        diagnostic_codes = {item["code"] for item in payload["diagnostics"]}
        self.assertIn("toolkit_release_file_conflict", diagnostic_codes)
        self.assertIn("toolkit_release_conflict", diagnostic_codes)

    def test_plain_version_cfg_must_contain_a_release_shaped_token(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            invalid_root = base / "invalid-cann"
            invalid_root.mkdir()
            (invalid_root / "version.cfg").write_text(
                "# package metadata\n[package]\nInstall_Path=/opt/cann\n",
                encoding="utf-8",
            )
            valid_root = base / "valid-cann"
            valid_root.mkdir()
            (valid_root / "version.cfg").write_text(
                "; release\n8.3.RC1\n",
                encoding="utf-8",
            )

            invalid_completed, invalid_payload = self.run_inspector(invalid_root)
            valid_completed, valid_payload = self.run_inspector(valid_root)

        self.assertEqual(invalid_completed.returncode, 0, invalid_completed.stderr)
        self.assertIsNone(invalid_payload["toolkit"]["resolved_release"])
        self.assertEqual(invalid_payload["toolkit"]["release_status"], "unknown")
        self.assertIn(
            "toolkit_release_plain_text_invalid",
            {item["code"] for item in invalid_payload["diagnostics"]},
        )
        self.assertEqual(valid_completed.returncode, 0, valid_completed.stderr)
        self.assertEqual(valid_payload["toolkit"]["resolved_release"], "8.3.RC1")
        self.assertEqual(
            valid_payload["toolkit"]["release_claims"][0]["provenance"]["line"], 2
        )

    def test_conflicting_component_requirements_are_not_selected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            write_version(
                root / "share/info/runtime/version.info",
                "9.1.0",
                "required_package_driver_version=25.3\n"
                "required_package_driver_version=25.5\n",
            )

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        component = payload["components"][0]
        self.assertNotIn("required_package_driver_version", component["requirements"])
        self.assertEqual(
            component["requirement_conflicts"],
            {"required_package_driver_version": ["25.3", "25.5"]},
        )
        self.assertEqual(
            [claim["provenance"]["line"] for claim in component["requirement_claims"]],
            [2, 3],
        )
        self.assertIn(
            "component_requirement_conflict",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_dangling_component_metadata_symlink_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            candidate = root / "share/info/broken/version.info"
            candidate.parent.mkdir(parents=True)
            candidate.symlink_to("missing-version.info")

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["components"], [])
        unreadable_paths = {
            item.get("path")
            for item in payload["diagnostics"]
            if item["code"] == "unreadable_path"
        }
        canonical_candidate = (
            pathlib.Path(os.path.realpath(root)) / "share/info/broken/version.info"
        )
        self.assertIn(str(canonical_candidate), unreadable_paths)

    def test_dangling_release_metadata_symlink_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            candidate = root / "compiler/version.info"
            candidate.parent.mkdir(parents=True)
            candidate.symlink_to("missing-version.info")

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["toolkit"]["release_status"], "unknown")
        canonical_candidate = pathlib.Path(os.path.realpath(root)) / "compiler/version.info"
        self.assertIn(
            str(canonical_candidate),
            {
                item.get("path")
                for item in payload["diagnostics"]
                if item["code"] == "unreadable_path"
            },
        )

    def test_inside_symlink_is_alias_and_outside_symlinks_are_not_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary)
            root = base / "cann"
            devkit = root / "share/info/asc-devkit/version.info"
            write_version(devkit, "9.1.0")
            (root / "compiler").mkdir(parents=True)
            (root / "compiler/version.info").symlink_to(
                pathlib.Path("../share/info/asc-devkit/version.info")
            )

            outside_version = base / "outside-version.info"
            outside_version.write_text("Version=99.0\n", encoding="utf-8")
            evil = root / "share/info/evil/version.info"
            evil.parent.mkdir(parents=True)
            evil.symlink_to(outside_version)

            outside_ini = base / "outside.ini"
            outside_ini.write_text(
                "SoC=AscendEscape\nNpuArch=escaped-arch\n", encoding="utf-8"
            )
            platform_link = root / "platform_config/escape.ini"
            platform_link.parent.mkdir(parents=True)
            platform_link.symlink_to(outside_ini)

            completed, payload = self.run_inspector(root, "--soc", "AscendEscape")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual([item["component_id"] for item in payload["components"]], ["asc-devkit"])
        canonical_root = pathlib.Path(os.path.realpath(root))
        self.assertIn(
            str(canonical_root / "compiler/version.info"), payload["components"][0]["aliases"]
        )
        self.assertEqual(payload["toolkit"]["resolved_release"], "9.1.0")
        self.assertEqual(payload["platform_configs"], [])
        self.assertEqual(payload["npu_arch"]["state"], "unknown")
        outside_diagnostics = [
            item
            for item in payload["diagnostics"]
            if item["code"] == "path_outside_toolkit_root"
        ]
        self.assertEqual(len(outside_diagnostics), 2)
        self.assertNotIn("99.0", completed.stdout)
        self.assertNotIn("escaped-arch", completed.stdout)

    def test_user_soc_is_toolkit_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "platform_config/Ascend310P3.ini"
            config.parent.mkdir(parents=True)
            config.write_text("NpuArch=dav-m200\n", encoding="utf-8")

            completed, payload = self.run_inspector(root, "--soc", "Ascend310P3")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["soc"]["selected_source"], "user_supplied")
        self.assertEqual(payload["npu_arch"]["value"], "dav-m200")
        self.assertEqual(payload["npu_arch"]["state"], "toolkit_metadata_only")
        self.assertEqual(payload["npu_arch"]["match_status"], "exact")

    def test_arch_specific_install_layout_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "aarch64-linux/data/platform_config/Ascend910B3.ini"
            config.parent.mkdir(parents=True)
            config.write_text("NpuArch=dav-c220-cube\n", encoding="utf-8")

            completed, payload = self.run_inspector(root, "--soc", "Ascend910B3")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_arch"]["value"], "dav-c220-cube")
        self.assertEqual(payload["npu_arch"]["state"], "toolkit_metadata_only")
        self.assertEqual(payload["npu_arch"]["match_status"], "exact")

    def test_repeated_identical_metadata_claims_are_not_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            write_version(root / "compiler/version.info", "9.1.0", "Version=9.1.0\n")
            config = root / "platform_config/Ascend310P3.ini"
            config.parent.mkdir(parents=True)
            config.write_text(
                "SoC=Ascend310P3\nNpuArch=dav-m200\nNpuArch=dav-m200\n",
                encoding="utf-8",
            )

            completed, payload = self.run_inspector(root, "--soc", "Ascend310P3")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["toolkit"]["resolved_release"], "9.1.0")
        self.assertEqual(payload["toolkit"]["release_status"], "resolved")
        self.assertEqual(payload["npu_arch"]["value"], "dav-m200")
        self.assertEqual(payload["npu_arch"]["match_status"], "exact")
        conflict_codes = {
            "toolkit_release_file_conflict",
            "platform_npu_arch_conflict",
        }
        self.assertTrue(
            conflict_codes.isdisjoint({item["code"] for item in payload["diagnostics"]})
        )

    def test_platform_match_is_exact_and_ambiguous_matches_do_not_guess(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            platform = root / "platform_config"
            platform.mkdir(parents=True)
            (platform / "first.ini").write_text(
                "Short_SoC_version=Ascend910B3\nNpuArch=arch-one\n", encoding="utf-8"
            )
            (platform / "second.ini").write_text(
                "SoC=Ascend910B3\nNpuArch=arch-two\n", encoding="utf-8"
            )
            (platform / "Ascend910B.ini").write_text(
                "NpuArch=shorter-name\n", encoding="utf-8"
            )

            completed, payload = self.run_inspector(root, "--soc", "Ascend910B3")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNone(payload["npu_arch"]["value"])
        self.assertEqual(payload["npu_arch"]["state"], "unknown")
        self.assertEqual(payload["npu_arch"]["match_status"], "ambiguous")
        self.assertEqual(len(payload["npu_arch"]["matched_platform_paths"]), 2)
        self.assertIn(
            "ambiguous_platform_match",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_substring_soc_does_not_match_and_build_target_stays_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "platform_config/Ascend910B.ini"
            config.parent.mkdir(parents=True)
            config.write_text("NpuArch=config-arch\n", encoding="utf-8")

            completed, payload = self.run_inspector(
                root,
                "--soc",
                "Ascend910B3",
                "--build-target",
                "requested-build-arch",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_arch"]["match_status"], "none")
        self.assertEqual(payload["npu_arch"]["value"], "requested-build-arch")
        self.assertEqual(payload["npu_arch"]["state"], "build_target_only")
        self.assertEqual(payload["platform_configs"][0]["npu_arch"]["value"], "config-arch")

    def test_no_hardware_or_cann_metadata_is_a_valid_unknown_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "empty-toolkit"
            root.mkdir()

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["toolkit"]["release_status"], "unknown")
        self.assertEqual(payload["components"], [])
        self.assertEqual(payload["driver"]["status"], "unknown")
        self.assertEqual(payload["soc"]["runtime_status"], "unknown")
        self.assertEqual(payload["npu_arch"]["state"], "unknown")

    def test_json_capture_supports_multiple_devices_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text(
                json.dumps(
                    {
                        "driver_version": "25.5.0",
                        "devices": [{"soc": "Ascend910B3"}, {"soc": "Ascend310P3"}],
                    }
                ),
                encoding="utf-8",
            )

            completed, payload = self.run_inspector(root, "--npu-capture", str(capture))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["driver"]["resolved_version"], "25.5.0")
        self.assertEqual(payload["npu_capture"]["status"], "recognized")
        self.assertEqual(payload["soc"]["runtime_status"], "conflict")
        self.assertIsNone(payload["soc"]["selected_for_resolution"])
        self.assertEqual(payload["npu_arch"]["state"], "unknown")
        self.assertIn(
            "runtime_soc_conflict",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_unrecognized_json_capture_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text("[]", encoding="utf-8")

            completed, payload = self.run_inspector(
                root, "--npu-capture", str(capture)
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_capture"]["status"], "unrecognized")
        self.assertIn(
            "capture_schema_unrecognized",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_malformed_json_capture_is_not_reinterpreted_as_key_value_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "platform_config/Ascend910B3.ini"
            config.parent.mkdir(parents=True)
            config.write_text("NpuArch=dav-c220\n", encoding="utf-8")
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text('{"soc": "Ascend910B3"', encoding="utf-8")

            completed, payload = self.run_inspector(
                root, "--npu-capture", str(capture)
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_capture"]["format"], "json")
        self.assertEqual(payload["npu_capture"]["status"], "unrecognized")
        self.assertEqual(payload["soc"]["runtime_status"], "unknown")
        self.assertEqual(payload["npu_arch"]["state"], "unknown")
        self.assertIn(
            "capture_json_invalid",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_boolean_json_identity_claims_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text(
                json.dumps({"soc": True, "driver_version": False}), encoding="utf-8"
            )

            completed, payload = self.run_inspector(root, "--npu-capture", str(capture))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_capture"]["status"], "unrecognized")
        self.assertEqual(payload["soc"]["runtime_status"], "unknown")
        self.assertEqual(payload["driver"]["status"], "unknown")
        self.assertIn(
            "capture_schema_unrecognized",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_fifo_capture_is_rejected_without_blocking(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("mkfifo is unavailable on this platform")
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            os.mkfifo(capture)

            completed, payload = self.run_inspector(
                root, "--npu-capture", str(capture), timeout=2
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error"]["code"], "invalid_npu_capture")

    def test_deeply_nested_json_capture_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text("[" * 2000 + "]" * 2000, encoding="utf-8")

            completed, payload = self.run_inspector(root, "--npu-capture", str(capture))

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(payload["error"]["code"], "invalid_npu_capture")

    def test_json_capture_nesting_limit_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"

            capture.write_text(
                "[" * JSON_NESTING_LIMIT + "]" * JSON_NESTING_LIMIT,
                encoding="utf-8",
            )
            accepted, accepted_payload = self.run_inspector(
                root, "--npu-capture", str(capture)
            )

            capture.write_text(
                "[" * (JSON_NESTING_LIMIT + 1)
                + "]" * (JSON_NESTING_LIMIT + 1),
                encoding="utf-8",
            )
            rejected, rejected_payload = self.run_inspector(
                root, "--npu-capture", str(capture)
            )

        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(accepted_payload["npu_capture"]["status"], "unrecognized")
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(rejected_payload["error"]["code"], "invalid_npu_capture")

    def test_json_nesting_check_ignores_brackets_and_escaped_quotes_in_strings(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            soc = 'Ascend910B3 ' + '[{"key": "\\\"value\\\""}]' * 100
            capture.write_text(json.dumps({"soc": soc}), encoding="utf-8")

            completed, payload = self.run_inspector(root, "--npu-capture", str(capture))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["soc"]["runtime_value"], soc)

    def test_text_output_escapes_control_characters_from_capture_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text(
                json.dumps({"soc": "Ascend910B3\n[ok] forged diagnostic\x1b[31m"}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--toolkit-root",
                    str(root),
                    "--npu-capture",
                    str(capture),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(
            r"SoC: Ascend910B3\n[ok] forged diagnostic\x1b[31m;",
            completed.stdout,
        )
        self.assertNotIn("\n[ok] forged diagnostic", completed.stdout)

    def test_casefold_equivalent_npu_arch_claims_are_not_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "platform_config/Ascend910B3.ini"
            config.parent.mkdir(parents=True)
            config.write_text(
                "NpuArch=DAV-C220\nNpuArch=dav-c220\n", encoding="utf-8"
            )

            completed, payload = self.run_inspector(root, "--soc", "Ascend910B3")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["npu_arch"]["value"], "DAV-C220")
        self.assertEqual(payload["npu_arch"]["match_status"], "exact")
        self.assertNotIn(
            "platform_npu_arch_conflict",
            {item["code"] for item in payload["diagnostics"]},
        )

    def test_runtime_soc_claims_use_the_same_casefold_exactness_as_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            config = root / "platform_config/Ascend910B3.ini"
            config.parent.mkdir(parents=True)
            config.write_text("NpuArch=dav-c220\n", encoding="utf-8")
            capture = pathlib.Path(temporary) / "capture.json"
            capture.write_text(
                json.dumps(
                    {
                        "devices": [
                            {"soc": "Ascend910B3"},
                            {"soc": "ASCEND910B3"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            completed, payload = self.run_inspector(root, "--npu-capture", str(capture))

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["soc"]["runtime_status"], "resolved")
        self.assertEqual(payload["soc"]["runtime_value"], "Ascend910B3")
        self.assertEqual(payload["npu_arch"]["value"], "dav-c220")
        self.assertEqual(payload["npu_arch"]["state"], "runtime_soc_correlated")

    def test_oversized_metadata_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            oversized = root / "share/info/runtime/version.info"
            oversized.parent.mkdir(parents=True)
            oversized.write_bytes(b"Version=9.1.0\n" + b"x" * (128 * 1024))

            completed, payload = self.run_inspector(root)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(payload["components"], [])
        self.assertIn("file_too_large", {item["code"] for item in payload["diagnostics"]})

    def test_explicit_oversized_or_non_file_capture_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary) / "cann"
            root.mkdir()
            oversized = pathlib.Path(temporary) / "oversized.capture"
            oversized.write_bytes(b"x" * (256 * 1024 + 1))
            directory_capture = pathlib.Path(temporary) / "capture-directory"
            directory_capture.mkdir()
            missing_capture = pathlib.Path(temporary) / "missing.capture"

            for capture in (oversized, directory_capture, missing_capture):
                with self.subTest(capture=capture.name):
                    completed, payload = self.run_inspector(
                        root, "--npu-capture", str(capture)
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertFalse(payload["success"])
                    self.assertEqual(payload["error"]["code"], "invalid_npu_capture")

    def test_implementation_has_no_execution_network_or_dynamic_loading_imports(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(SCRIPT))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
        self.assertTrue(
            imported_roots.isdisjoint(
                {"ctypes", "http", "requests", "socket", "subprocess", "urllib"}
            ),
            imported_roots,
        )
        forbidden_calls: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id in {
                "eval",
                "exec",
                "__import__",
            }:
                forbidden_calls.append(node.func.id)
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and (
                    node.func.attr in {"system", "popen"}
                    or node.func.attr.startswith("exec")
                    or node.func.attr.startswith("spawn")
                )
            ):
                forbidden_calls.append(f"os.{node.func.attr}")
        self.assertEqual(forbidden_calls, [])
        self.assertNotIn("read_bytes", source)

    def test_invalid_explicit_root_returns_structured_error(self) -> None:
        missing = pathlib.Path(tempfile.gettempdir()) / "codex-missing-cann-state-root"
        if missing.exists():
            self.skipTest(f"unexpected fixture path exists: {missing}")

        completed, payload = self.run_inspector(missing)

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
