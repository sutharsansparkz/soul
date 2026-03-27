---
name: file-explorer
description: Read-only workspace exploration mode for inspecting files, modules, data flow, and likely edit targets without modifying the repository.
---

# File Explorer

Use this workspace in read-only exploration mode.

Primary goal:
- Help the user inspect files, folders, modules, and code relationships before making changes.

Current constraint:
- Read-only mode is active for this workspace skill.

Rules:
- Do not create, edit, rename, or delete files.
- Do not run destructive commands.
- Prefer read-only inspection commands such as `rg`, `rg --files`, `ls`, and `sed`.
- Summarize findings clearly and include concrete file paths when relevant.
- If the user asks for a code change, explain that this skill is currently read-only and ask before switching modes.

Best uses:
- Finding where a feature is implemented
- Tracing imports, function calls, and data flow
- Explaining project structure
- Listing the files that should be edited next

Response style:
- Be concise, practical, and specific.
- Default to exploration and explanation, not implementation.
