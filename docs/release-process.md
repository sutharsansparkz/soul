# Release Process

SOUL releases should come from `main` only.

## Intended Flow

1. Land work on `development` or another non-release branch.
2. Open a pull request into `main`.
3. Let the `Tests` workflow pass.
4. Merge to `main`.
5. Let `.github/workflows/release.yml` run Python Semantic Release.

That workflow is responsible for:

- updating `pyproject.toml` and `soul/__init__.py`
- updating `CHANGELOG.md`
- creating the `v*` git tag
- creating the GitHub Release entry
- uploading built `dist/` artifacts to the release

## Commit Expectations

The release workflow uses the Conventional Commits parser.

- `feat:` triggers a minor release
- `fix:` and `perf:` trigger a patch release
- `BREAKING CHANGE:` or `!` semantics trigger a major release

Commits such as release bot commits and merge commits are excluded from the
generated changelog.

## Maintainer Checklist

Apply these GitHub settings manually because they cannot be enforced from the
repository contents alone:

- protect `main`
- require pull requests before merging into `main`
- require the `Tests` workflow checks to pass before merge
- require conversation resolution before merge
- block force pushes and branch deletion on `main`

## Notes

- `CHANGELOG.md` is owned by semantic-release and should not be deleted.
- Version numbers should not be bumped manually on feature branches.
- GitHub Pages deployment is separate from package release automation. Pages is
  handled by `.github/workflows/pages.yml`.
- `workflow_dispatch` exists on the release workflow as a manual retry path if
  the release job itself fails after a valid merge to `main`.
