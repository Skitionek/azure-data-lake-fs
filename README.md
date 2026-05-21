# Automated-reppo

A GitHub repository template providing far-reaching Copilot and automation integration, distilled from common patterns across private repositories.

## What's included

| File | Purpose |
|------|---------|
| `.github/copilot-instructions.md` | Copilot coding guidelines: Conventional Commits, Changelog conventions |
| `.github/CODEOWNERS` | Assign default reviewers to all files |
| `.github/FUNDING.yml` | GitHub Sponsors link |
| `.github/dependabot.yml` | Automated dependency updates (GitHub Actions + project ecosystems) |
| `.github/workflows/codeql.yml` | CodeQL Advanced security scanning on push/PR/schedule |
| `.github/workflows/copilot-auto-fix.yml` | Posts a `@copilot` comment when CI fails on a PR, asking it to propose a fix |
| `.github/workflows/dependabot-automerge.yml` | Auto-approves and squash-merges Dependabot PRs |
| `.github/workflows/lint.yml` | MegaLinter via reusable `Skitionek/lint` action: lints changed files on PRs and opens auto-fix PRs when fixable |
| `.github/workflows/megalinter-auto-approve.yml` | Auto-approves MegaLinter fix PRs so they can be merged immediately |
| `CHANGELOG.md` | Keep-a-Changelog template, updated by Copilot on every user-facing change |

## Usage

1. Click **Use this template** → **Create a new repository**.
2. Adapt `.github/dependabot.yml` to your project's package ecosystems.
3. Uncomment the language matrix entries in `.github/workflows/codeql.yml` that match your stack.
4. If you want the Copilot auto-fix comment to trigger on a workflow other than `Tests`, update the `workflows:` list in `.github/workflows/copilot-auto-fix.yml`.
5. To auto-merge Dependabot PRs only for minor/patch updates, edit the metadata check in `.github/workflows/dependabot-automerge.yml`.

## Automation flow

```
Push / PR
  │
  ├─► MegaLinter (lint.yml)
  │     └─► Opens megalinter-fixes-pr-* branch → auto-approved (megalinter-auto-approve.yml)
  │
  ├─► CodeQL (codeql.yml)
  │
  ├─► Your Tests workflow (add tests.yml to your repo)
  │     └─► On failure → @copilot comment (copilot-auto-fix.yml)
  │
  └─► Dependabot PRs → auto-approved + auto-merged (dependabot-automerge.yml)
```
