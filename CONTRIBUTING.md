# Contributing to Promptline

Promptline is a downstream of [Terminator](https://github.com/gnome-terminator/terminator).
Read [CLAUDE.md](CLAUDE.md) for how the code is laid out and the product rules, and
[doc/UPSTREAM.md](doc/UPSTREAM.md) before touching Terminator's own files.

## Branches

| Branch | What it is |
| --- | --- |
| `master` | Development. The next minor or major release (0.2.0, 1.0.0) is cut from here. |
| `release/X.Y.x` | Maintenance for one release series, e.g. `release/0.1.x`. Patch releases (0.1.1, 0.1.2) are tagged here. |
| `fix/…`, `feature/…`, `merge-upstream-vX.Y.Z` | Your work. Branch from the branch you will open the pull request against. |

`master` and `release/*` only change through pull requests: rulesets on GitHub block
direct pushes, force pushes and deletion, for maintainers too, and the tests must pass.
Release tags (`v*`) can't be moved or deleted once pushed.

History is public, so never rebase or force-push a shared branch. Rebasing your own
branch before anyone else has based work on it is fine.

## Making a change

1. Branch from `master` (new work) or from `release/X.Y.x` (a fix for users of that
   release that shouldn't wait for the next minor release).
2. Add a test that fails without your change. Run the suite:
   ```sh
   xvfb-run -a pytest
   ```
3. Write commit messages that say what changed and why: a short summary line, then
   the reasoning.
4. Open a pull request against the branch you started from. CI runs the tests (and,
   into a release branch, builds and checks the Debian package).
5. Merge with a merge commit, not a squash, so fixes can be merged between branches
   without duplicate commits.

A fix merged into a release branch reaches `master` when the release branch is merged
forward (see below). Don't open a second PR with the same fix against `master`.

## Releasing

A patch release, e.g. 0.1.2 from `release/0.1.x`:

1. Open a pull request into `release/0.1.x` that bumps `APP_VERSION` in
   `promptlinelib/version.py` and adds a matching `debian/changelog` entry (`dch -v 0.1.2`).
   The changelog bullets become the release notes. CI checks that the versions agree
   and builds the `.deb`.
2. Merge it, then tag the merge commit and push the tag:
   ```sh
   git switch release/0.1.x && git pull
   git tag -a v0.1.2 -m "Promptline 0.1.2"
   git push origin v0.1.2
   ```
   `.github/workflows/release.yml` builds the `.deb` again, checks the tag matches the
   version, and publishes the GitHub release with the package and `SHA256SUMS`.
3. Open a pull request from `release/0.1.x` into `master` to bring the fixes forward,
   and resolve any conflicts there.

A minor or major release, e.g. 0.2.0: create `release/0.2.x` from `master`, then follow
the steps above on that branch. The old series gets fixes only while it's supported.

## Upstream Terminator

Merge upstream releases into a `merge-upstream-vX.Y.Z` branch and open a pull request
against `master`; see [doc/UPSTREAM.md](doc/UPSTREAM.md).
