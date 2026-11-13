# Git session scripts

EXEC supports inline argv/interpreter scripts for short one-off commands and commit-pinned CrossZoneScript scripts for reusable or evolving code. Session-local named scripts, read/update commands, registries, manifests and hash-conflict content export are removed.

Git execution is {git:"session",commit:<40 hex>,entry:<relative script path>,args:{}}. Repository is fixed to https://github.com/LingquLab/CrossZoneScript; branch is the bound session UUID. Require commit reachability from that branch and snapshot regular files. Never execute a moving branch HEAD. Pass JSON parameters via --args-file; cwd stays the run workspace.

Reuse EXEC receipts, cancellation, task identity and durable outbox. Preparation failures return REJECTED with an explicit code/detail. Command and review timeouts are independent; Git fetch has a 120-second timeout. Advertise only exec.git-session.v1.

Validate pinned commit execution, rejection of removed protocol forms, branch isolation and legacy EXEC compatibility. Blue edits scripts with ordinary commits on its session branch using the local Codex automation author identity. No green Git pushes or automatic history changes.
