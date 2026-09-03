# Ascend C Development

[中文文档](./README_CN.md)

This ZCode and Codex plugin provides version-aware workflows for Ascend C operator implementation, API research, code review, environment inspection, NPU status, CANN setup, and runtime debugging.

## Use

Ask the agent to develop or migrate an operator, check an Ascend C API, review Host/Tiling/Kernel code, inspect an Ascend environment, view NPU occupancy, install or repair CANN, or diagnose a runtime failure. Eight focused skills are selected independently from the request.

## Dependencies and effects

- Network: documentation searches may access Huawei documentation and public GitCode content. Remote environment and NPU checks may use SSH when the user names a host.
- Commands: skills may run local build, test, CANN, NPU, Git, Python, Ruby, curl, or SSH commands appropriate to the requested task.
- Files: development and setup workflows can modify the active repository or explicitly selected environment. Review, documentation search, status, and environment inventory remain read-only unless the user requests changes.
- Services: complete runtime validation requires a compatible Ascend device, driver, firmware, CANN toolkit, and operator package.
- Hooks and MCP: none.

Some skills are adapted from TileXR material. Provenance is recorded in the repository `THIRD_PARTY_NOTICES.md`; the plugin is distributed under its bundled CANN Open Software License Agreement Version 2.0.
