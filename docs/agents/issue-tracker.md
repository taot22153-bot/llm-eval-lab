# Issue Tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues:

- Repository: `taot22153-bot/llm-eval-lab`
- URL: <https://github.com/taot22153-bot/llm-eval-lab/issues>

Prefer the `gh` CLI for issue and pull-request operations. If `gh` is not
available on the current workstation, use the authenticated GitHub REST API
through the existing Git Credential Manager session. Never print or persist an
access token in repository files, command output, or logs.

## Conventions

- Create an issue: `gh issue create --title "..." --body "..."`
- Read an issue: `gh issue view <number> --comments`
- List issues: `gh issue list --state open --json number,title,body,labels`
- Comment: `gh issue comment <number> --body "..."`
- Add or remove labels: `gh issue edit <number> --add-label "..."` or
  `gh issue edit <number> --remove-label "..."`
- Close an issue: `gh issue close <number> --comment "..."`

Infer the repository from `git remote -v` when running inside the clone.

## Pull Requests as a Triage Surface

**PRs as a request surface: no.**

Pull requests are used to review and merge implementation work. External pull
requests are not treated as incoming feature requests by the `triage` workflow.

GitHub shares one number space across issues and pull requests. If a reference
such as `#42` is ambiguous, resolve its type before acting on it.

## Skill Semantics

When a skill says "publish to the issue tracker," create a GitHub issue. When a
skill says "fetch the relevant ticket," read the complete GitHub issue body,
labels, and comments.
