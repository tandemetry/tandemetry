# Releasing

Releases are published to PyPI by `.github/workflows/release.yml` through
[trusted publishing](https://docs.pypi.org/trusted-publishers/): the workflow proves its identity
to PyPI with a short-lived GitHub token, so no PyPI credentials are stored in the repository.
PyPI only accepts it from this repository, the workflow `release.yml` and the GitHub environment
`pypi`; all three names must match the publisher configured on PyPI.

## Procedure

1. Set the new version in `pyproject.toml`, run `uv lock`, merge the change through a PR.
2. Create a GitHub Release on `main` with the tag `v<version>` (for example `v0.0.1`).
3. Approve the deployment to the `pypi` environment if required reviewers are configured.
4. Verify: `pip install tandemetry==<version> && tandemetry --version`.

The workflow fails before publishing if the tag differs from the version in `pyproject.toml`.
A version published to PyPI can never be replaced: fix forward with a new version.
