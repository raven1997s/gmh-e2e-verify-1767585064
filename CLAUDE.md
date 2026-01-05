# Claude Code Project Configuration

## Available Skills

- **Git Merge Helper**: Located in `.claude/skills/git-merge-helper`.
  - Use this skill for ALL git merge operations.
  - Do NOT use native git commands directly.

## Commands

- **merge**: `python3 .claude/skills/git-merge-helper/scripts/merge_executor.py` - Safely merges current branch to target (default: main).
- **mh**: `python3 .claude/skills/git-merge-helper/scripts/merge_executor.py` - Alias for merge.
