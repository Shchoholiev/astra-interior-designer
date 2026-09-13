# Verify the plugin source

At first use of this plugin in a task, resolve the copy containing the skill being read. Use its `.codex-plugin/plugin.json` to record the plugin root and version in the task's local progress record. Record a Git revision and relevant dirty state when available, or a packaged build revision when provided. If neither exists, mark the revision unknown and continue with the accessible files; Git is not a runtime dependency.

Record the actual skill and reference paths as they are read. Reuse this record for subsequent stages and refresh it when the source changes. Do not load every skill merely to inventory the plugin.

When the user specifies a project or plugin copy, compare that intended source with the resolved files. Another worktree containing a newer version does not prove the current agent or sandbox loaded it. If copies differ or required skills are missing, identify the mismatch and use the requested accessible source within the task's scope. Do not silently switch branches, overwrite installations, or mix references from different versions. If the requested source is unavailable, report the limitation rather than claiming it was used.
