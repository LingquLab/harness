# Cross Zone Development

[中文文档](./README_CN.md)

This ZCode and Codex plugin coordinates GitHub Issue handoffs when an external model develops code and an internal DeepSeek or GLM model must test it against protected services.

## Use

Ask the agent to prepare, execute, or consume a cross-zone debugging handoff. The `cross-zone-development` skill selects the blue- or green-zone workflow from the model identity. An unknown model family stops before modifying GitHub and asks for a trusted zone designation.

The blue-zone agent creates a bounded handoff issue and later consumes the sanitized result. The green-zone agent performs service checks and returns only conclusions, case identifiers, status, timing, and the next requested change. It does not return source code, bulk logs, internal endpoints, payloads, stack traces, credentials, or exported artifacts.

## Dependencies and effects

- Network: reads and writes GitHub Issues. Private repositories require an authenticated GitHub integration, GitHub CLI, or an existing HTTPS Git credential.
- Commands: the fallback helpers run Python, Git credential lookup, and curl. Their curl requests always use `--ssl-no-revoke` and `--insecure`.
- Files: the helpers use bounded temporary files for request data and remove them after use. The skill may edit the active repository when the user asks the blue-zone agent to apply returned findings.
- Services: green-zone checks use only the protected service access already available to that agent.
- Hooks and MCP: none.

The plugin contains original LingquLab material and is licensed under the repository MIT license.
