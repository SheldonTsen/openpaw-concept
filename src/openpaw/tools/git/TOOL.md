---
name: git
description: Execute git commands for version control operations
parameters:
  type: object
  properties:
    command:
      type: string
      description: Git command to execute (without 'git' prefix)
    timeout:
      type: integer
      description: Timeout in seconds (default 30)
      default: 30
  required:
    - command
metadata:
  type: cli
  command_template: "git {command}"
  tier: experimental
  priority: 7
  retry_policy:
    maximum_attempts: 2
    backoff_coefficient: 1.5
---

# Git Version Control

Execute git commands for version control operations including status, commits, branches, and remote operations.

## Usage

Use this tool to check repository status, create commits, manage branches, view history, and interact with remote repositories.

## Examples

```bash
# Check repository status
git status

# View commit history
git log --oneline -10

# Show recent changes
git diff HEAD~1

# Create a new branch
git checkout -b feature/new-feature

# View all branches
git branch -a

# Show specific commit
git show abc123

# Check for uncommitted changes
git status --porcelain

# View file history
git log --follow -- path/to/file.py
```

## Common Operations

### Status & Info
- `status` - Show working tree status
- `log --oneline -N` - Show last N commits
- `diff` - Show changes
- `show HASH` - Show specific commit

### Branching
- `branch` - List branches
- `checkout -b NAME` - Create and switch to branch
- `branch -d NAME` - Delete branch
- `merge BRANCH` - Merge branch

### Staging & Commits
- `add FILE` - Stage file
- `add .` - Stage all changes
- `commit -m "message"` - Create commit
- `commit --amend` - Amend last commit

### Remote Operations
- `fetch` - Fetch from remote
- `pull` - Fetch and merge
- `push` - Push to remote
- `remote -v` - List remotes

## Notes

- Git must be initialized in workspace (`git init`)
- Requires git configuration (user.name, user.email)
- Network operations may timeout on slow connections
- Use `--` separator for file paths to avoid ambiguity
- Some operations may require authentication
- Repository state persists within workflow

## Security Considerations

- **Never commit secrets**: API keys, passwords, tokens
- **Review before push**: Check what you're pushing
- **Use .gitignore**: Exclude sensitive files
- **Check remote URL**: Verify before pushing

## Common Use Cases

- Checking repository status
- Viewing commit history
- Creating branches for features
- Reviewing changes before commit
- Investigating file history
- Syncing with remote repository
- Resolving merge conflicts
