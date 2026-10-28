# Launch checklist

Manual steps for the maintainer, in order. Steps marked Done were completed on the dates shown.

1. **Push the data branch.** Done on 2026-10-27. The `data` branch holds the backfilled history and the first live forecasts (2026-10-27). It contains derived CPCB and Grid-India values, so send the requests in step 2 now.
2. **Ask CPCB and Grid-India for permission to republish derived daily values.** Drafts are in `docs/launch/permission_requests.md`. CPCB's policy allows downloading, but other use needs approval (ccb.cpcb@nic.in). Grid-India's terms could not be read. If you prefer to wait for replies, keep the repository's data branch unpushed (or the repository private) until then.
3. **Protect branches.** In Settings > Branches, add rules for `main` (require pull request review and passing `ci`) and `data` (block force pushes and deletion). Add a CODEOWNERS entry for `.github/` and `submissions/`.
4. **Create the `run-submission` and `source-health` labels.** Settings > Labels. Only maintainers can apply labels, which is what gates submission runs. Done on 2026-10-28.
5. **Enable GitHub Pages.** Settings > Pages > Source: "GitHub Actions". The `score-and-site` workflow deploys to it. Done on 2026-10-28.
6. **Allow Actions to write.** Settings > Actions > General > Workflow permissions: "Read and write permissions". The workflows narrow this per job. Also tick "Require approval for all outside collaborators" for fork PR workflows.
7. **Switch the arena on.** Settings > Secrets and variables > Actions > Variables: add `ARENA_ENABLED` = `true`. Until then, scheduled jobs skip themselves. Done on 2026-10-28.
8. **Run the first cycle by hand.** Actions > daily-forecast > Run workflow. Check that all model jobs finish, that `commit` pushes `forecasts/<date>/forecasts.parquet` and a manifest line to `data`, and that a `.ots` proof was written. Done on 2026-10-28. All model jobs passed and the 2026-10-28 forecasts and proof are on `data`.
9. **Check scoring and the site.** Actions > score-and-site > Run workflow. Open the Pages URL. Put it in the README in place of `<LEADERBOARD_URL>` and in the repository's About box. Done on 2026-10-28. The site is at https://tharun0127.github.io/Bhavishya/ and the README links to it.
10. **Verify the first scheduled run.** The next day after 11:15 IST, confirm the scheduled run happened and that `bhavishya verify` passes on a fresh clone of `data`.
11. **data.gov.in API key (for Agmarknet, planned).** Register at https://www.data.gov.in/, sign in, open My Account, copy the API key. Put it in `.env` as `DATA_GOV_IN_API_KEY` locally, and in GitHub as an Actions secret with the same name. The Agmarknet loader still has to be written and added as panel v2.
12. **PyPI account and trusted publishing.** Create a PyPI account with 2FA. On https://pypi.org/manage/account/publishing/ add a pending trusted publisher: project `bhavishya`, owner `Tharun0127`, repository `Bhavishya`, workflow `release.yml`, environment `pypi`. In GitHub, create the environment `pypi` (Settings > Environments), optionally with required reviewers.
13. **First release.** Check `src/bhavishya/_version.py` says `0.1.0` and `CHANGELOG.md` is current. Then `git tag v0.1.0 && git push origin v0.1.0`. The `release` workflow builds and publishes. Confirm with `pip install bhavishya` in a clean environment.
14. **Announce.** Only after steps 8 to 10 work. Drafts are in `docs/launch/`. Nothing has been posted or sent.
15. **After 28 days.** Check that rankings switched from provisional to ranked as expected, and read the first leaderboard critically before sharing it.
16. **After 90 days.** Run the analyses in `docs/PAPER_OUTLINE.md`.
