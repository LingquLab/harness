# Ascend C Development

[中文文档](./README_CN.md)

This Codex plugin provides version-aware workflows for Ascend C operator implementation, API research, code review, environment inspection, NPU status, CANN setup, and runtime debugging.

## Use

Ask the agent to develop or migrate an operator, check an Ascend C API, review Host/Tiling/Kernel code, inspect an Ascend environment, view NPU occupancy, install or repair CANN, or diagnose a runtime failure. Eight focused skills are selected independently from the request.

## Skills

The plugin contains eight independently triggered skills:

| Skill | Use when |
|---|---|
| `ascendc-api-best-practices` | Implementing or debugging Ascend C API usage and alignment, buffer, precision, or pipeline behavior |
| `ascendc-code-review` | Reviewing Host, Tiling, Kernel, SIMT, build, or operator changes |
| `ascendc-docs-search` | Locating version-matched local or official Ascend C documentation and examples |
| `ascendc-env-check` | Performing read-only CANN environment and NPU visibility diagnostics |
| `ascendc-npu-status` | Checking JSON-listed Ascend NPU process occupancy locally or over SSH |
| `ascendc-operator-development` | Developing or migrating a complete registered or direct-launch Ascend C operator through layered validation |
| `ascendc-runtime-debug` | Diagnosing runtime, Tiling, launch, device-exception, hang, precision, or performance failures from bounded evidence |
| `cann-env-setup` | Planning or carrying out a guarded, version-matched CANN installation or repair |

## Dependencies and effects

- Network: documentation searches may access Huawei documentation and public GitCode content. Remote environment and NPU checks may use SSH when the user names a host.
- Commands: skills may run local build, test, CANN, NPU, Git, Python, Ruby, curl, or SSH commands appropriate to the requested task.
- Files: development and setup workflows can modify the active repository or explicitly selected environment. Review, documentation search, status, and environment inventory remain read-only unless the user requests changes.
- Services: complete runtime validation requires a compatible Ascend device, driver, firmware, CANN toolkit, and operator package.
- Hooks and MCP: none.

Distributed under the bundled [CANN Open Software License Agreement Version 2.0](LICENSE). Attribution is available in [third-party notices](../../THIRD_PARTY_NOTICES.md).
