# Releasing: details

The concept is in docs/Releasing.md.

## When

After every change that is finished and tested, in the same session: a fix, a feature or a docs change. Several
changes made together go out as one release.

## Numbering

`MAJOR.MINOR.PATCH`, in two places that must agree: `version` in `pyproject.toml` and `__version__` in
`verbaline/__init__.py`. Before 1.0 the patch number goes up for every release; a change to the project API that
breaks an existing `verbaline.toml` or adapter raises the minor number and says so in the change log.

## Steps

1. **Change log.** Rename `## Unreleased` in CHANGELOG.md to `## X.Y.Z (YYYY-MM-DD)` (or write the entry): one bold
   lead per change, written for the people who use the studio, saying what they will notice.
2. **Version.** Set it in both files above. `grep -rn` the old number for docs that quote it.
3. **Checks.** `python tests/test_verbaline.py` passes, and again under a non-UTF-8 locale
   (`PYTHONUTF8=0 LC_ALL=en_US.CP1252 python tests/test_verbaline.py`), which stands in for Windows' code page.
4. **Commit** the release as `X.Y.Z: <one line>`.
5. **Windows.** Push the commit to a temporary branch and wait for `.github/workflows/windows.yml` to pass
   (`gh run watch --exit-status`). Only a green run goes to `main`; delete the temporary branch after.
6. **Tag.** An annotated tag `vX.Y.Z` on that commit, pushed.
7. **Release files.** The zip is the tagged tree, made by
   `git archive --format=zip --prefix=VerbalineForGames-X.Y.Z/ -o VerbalineForGames-X.Y.Z.zip vX.Y.Z`, with a
   `SHA256SUMS` file beside it (`sha256sum VerbalineForGames-X.Y.Z.zip > SHA256SUMS`).
8. **Release.** `gh release create vX.Y.Z --verify-tag --title "Verbaline For Games X.Y.Z"` with the change-log entry
   as the notes and both files attached. Check that it is marked Latest.
9. **Running studios.** Move each install to the tag (`git fetch --tags && git checkout vX.Y.Z`) and restart it only
   when its jobs panel shows nothing running or queued. A page left open across the update needs a reload.
