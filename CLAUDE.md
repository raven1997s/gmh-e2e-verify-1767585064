# Claude Code Project Configuration

## Available Skills

- **Git Merge Helper**: Located in `.claude/skills/git-merge-helper`.
  - Use this skill for ALL git merge operations.
  - Do NOT use native `git merge` commands directly.
  - Triggers: "merge to", "合并 to", "合并到", "/mh".

## Guidelines

When the user asks to merge branches, ALWAYS invoke the `git-merge-helper` skill.

