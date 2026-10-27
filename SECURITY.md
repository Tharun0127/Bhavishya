# Security

## Reporting

Report vulnerabilities privately through GitHub's "Report a vulnerability" button on the Security tab. Please do not open a public issue.

## Threat model

### Assets

1. **Forecast integrity.** Nobody, including maintainers, should be able to change a forecast after its outcome is known without it being detectable.
2. **Repository write access** (the `GITHUB_TOKEN` with `contents: write`, used by the daily jobs).
3. **Future secrets.** There are none today. A PyPI release uses OIDC trusted publishing, not a stored token.
4. **Runner resources.**

### Threats and controls

| Threat | Control |
|---|---|
| A malicious model submission tries to steal tokens or push code | Submissions run only on `pull_request` (never `pull_request_target`). Fork PRs get a read-only token and no secrets. The job sets `permissions: contents: read` and `persist-credentials: false`. |
| A submitter pushes new code after a maintainer approved the old code | The workflow runs only on the `labeled` event and checks out the exact head commit at label time. New pushes do not run until a maintainer labels again. |
| A submission reads future outcomes or exfiltrates data | It runs in Docker with `--network none`, a read-only root filesystem, `--cap-drop ALL`, `no-new-privileges`, and only the history file mounted read-only. The history file is truncated at the cutoff before the container starts. |
| A submission exhausts resources | `--memory 6g`, `--cpus 2`, `--pids-limit 256`, 30-minute timeout per run, 75-minute job timeout. |
| A submission returns malformed or poisoned output | The host re-validates output with trusted code (row set, finite values, sorted quantiles) and ignores any cutoff or dates the container wrote. |
| A merged submission turns malicious later | Merged code is reviewed. In the daily job, submissions run in the same sandbox with no write token; only the separate commit job can write, and it runs only trusted code from `main`. |
| A maintainer edits a past forecast | Each forecast file's SHA-256 is in an append-only manifest, committed and pushed before outcomes exist, and anchored with an OpenTimestamps proof. `bhavishya verify` recomputes all hashes. Rewriting history would contradict clones, forks and the timestamp proofs. |
| A source serves bad data | Data contracts reject the file; the source is skipped for the day, a gap is recorded and an issue is opened. |
| A modified workflow in a PR | Fork PR workflows run with a read-only token and no secrets, so a modified workflow gains nothing. Maintainers should protect `.github/` with CODEOWNERS and require review. |

### Known limits

- Built-in model jobs run in GitHub-hosted runners with network access (to download weights). They run only trusted code from `main`.
- OpenTimestamps proofs are pending for a few hours until the calendars anchor them in Bitcoin. Until then, the git commit time on GitHub is the main evidence.
- Git history on GitHub can be force-pushed by an admin. Branch protection on `data` (no force push, no deletion) is a launch checklist item. Forks and the timestamp proofs make silent rewrites detectable.
