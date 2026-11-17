# Releasing coaxi

The workflow is `.github/workflows/release.yml`, displayed as
**Publish Python package** in GitHub Actions.
**Pushing a `v*` tag starts a production PyPI release**, subject to validation and
the `pypi` environment's protection rules. The tag must match the project version.
Manual dispatch remains available for either `pypi` or `test-pypi` and defaults
to `test-pypi`. Branch pushes, pull requests and GitHub Release events do not
start this workflow.

## One-time configuration

1. Enable GitHub Actions in the repository and allow the pinned actions used by
   the workflow.
2. Create GitHub environments named **`test-pypi`** and **`pypi`**.
   Restrict deployments to release tags, for example `v*`, and configure required
   reviewers for production where your GitHub plan and team setup permit it.
   These protection rules are configured in GitHub, not by the YAML file.
3. Configure a GitHub Actions Trusted Publisher separately on TestPyPI and PyPI:

   | Field | TestPyPI | PyPI |
   |---|---|---|
   | Project name | `coaxi` | `coaxi` |
   | Owner | Your GitHub user/organisation | Same |
   | Repository | This repository's GitHub name | Same |
   | Workflow filename | `release.yml` | `release.yml` |
   | Environment | `test-pypi` | `pypi` |

   Use a pending publisher under your account's **Publishing** page for a new
   project; use the project's publishing settings for an existing owned project.
   A pending publisher does not reserve a project name. The first upload creates
   the project. PyPI and TestPyPI have separate accounts and configuration.
4. Enable two-factor authentication on the package-index accounts. Do not add
   PyPI passwords or API tokens to GitHub Secrets: this workflow uses OIDC
   Trusted Publishing.

The environment spelling must match exactly, including the hyphen in
`test-pypi`. The workflow must be on the default branch before GitHub offers
**Run workflow**, and it must also be present at the release tag.
Restrict who can create or update release tags: a matching tag push now
authorises production publishing, subject to the `pypi` environment rules.

## Release a new version

1. Bump `pyproject.toml` to the new version and update `uv.lock` with `uv lock`.
   Review and commit the release files after running the usual checks.
   Never reuse a version already published on the destination index.
2. Push the reviewed commit to the repository, then create and push an annotated
   tag at that commit. For example, for a future `1.0.1` release:

   ```sh
   git tag -a v1.0.1 -m "coaxi 1.0.1"
   git push origin v1.0.1
   ```

   **The tag push starts a real production upload**, after validation and any
   required `pypi` approval. This includes pre-release versions if their tags
   match the project version; they are not routed to TestPyPI.
3. Review the run and approve the `pypi` deployment if required. Check the
   release page, rendered README, distribution hashes and both files on PyPI.
4. Install the new version from production PyPI in a fresh consumer environment
   outside the checkout.

The existing `v1.0.0` tag and release must remain unchanged. To use this updated
workflow, new tags must point to commits containing it. Push release tags
individually: GitHub does not create tag-push events for pushes containing more
than three tags. A tag pushed by another workflow using the repository's
`GITHUB_TOKEN` normally does not trigger this workflow; use manual dispatch in
that case.

Concurrency is scoped to the version ref and index, so different versions do
not replace each other's pending runs. Duplicate runs for the same ref/index
share GitHub's one-running/one-pending concurrency group; a newer pending run
can replace an older pending duplicate.

## Optional manual runs

Open **Actions → Publish Python package → Run workflow**.
Select a matching version tag as the workflow ref, not `master`, and choose
the destination. For example:

```sh
gh workflow run release.yml --ref v1.0.1 -f destination=test-pypi
```

This is an actual TestPyPI upload, not a dry run. Manual production runs use
`-f destination=pypi`, for example when recovering a release that did not upload.
Avoid manually starting production while the tag-triggered run is pending;
duplicate uploads fail. A manual TestPyPI run does not gate the automatic PyPI run.

If TestPyPI validation is needed **before** production, use an unpublished
pre-release version/tag and hold the corresponding `pypi` environment approval
while running the tag manually against TestPyPI. Cancel the pending production
run if it should not publish. Without a required approval, pushing that tag
can publish it to PyPI immediately after validation.

After a TestPyPI run, test installation outside the checkout. One way to keep
runtime dependencies on production PyPI is to download the **specific wheel**
from the TestPyPI release's Files tab, check its SHA-256 against the workflow's
log, and use:

```sh
uv venv --python 3.13 /tmp/coaxi-release-consumer
uv pip install --python /tmp/coaxi-release-consumer/bin/python \
  --index-url https://pypi.org/simple/ /absolute/path/to/coaxi-1.0.1-py3-none-any.whl
/tmp/coaxi-release-consumer/bin/python -I -c \
  'import coaxi; from importlib.metadata import version; print(version("coaxi"), coaxi.__file__)'
```

Use a fresh destination directory for the consumer. Avoid adding TestPyPI as
an extra dependency index: it need not contain the runtime dependency graph.

Each run validates and publishes its own exact pair of files. Separate TestPyPI
and PyPI runs rebuild from the same tag; they are not byte-for-byte artefact
promotion, and isolated build dependencies are not pinned by `uv.lock`.

## What the workflow checks

- The full Git ref must equal `refs/tags/v` plus the static project version.
  Branches and mismatched tags fail; the project and lockfile must agree.
- Tag pushes select `pypi`. Manual dispatch requires a known destination.
  The guard's resolved destination controls the publish job's condition,
  GitHub environment and upload URL.
- Ubuntu 24.04 x86-64, uv 0.13.7, Python 3.13.5 and the checksum-pinned official
  NVC 1.21.1 package form the initial CI toolchain. Development packages come
  from `uv.lock`. Update these pins deliberately; this is not a multi-platform
  compatibility claim.
- Pyrefly, Ruff formatting/lint and the full Python/NVC test suite must pass.
- `uv build --no-sources` creates an sdist and a wheel from that sdist in a fresh
  directory. The build-free `uv run python -m tests.test_distribution --dist DIRECTORY` command
  checks that exact pair, metadata, source contents, licence and typing marker.
  It installs the wheel into an isolated runtime-only consumer, checks import
  origins/version, and runs the packaged VHDL example in both cocotb write modes.
- The upload artefact contains only that wheel and sdist. Only the separate
  publish job has `id-token: write`; it downloads the build job's artefact ID
  from the same run. It does not check out, rebuild or execute project code.
  The pinned PyPA action verifies metadata before upload and generates
  provenance attestations.

Changes to the tag trigger and event routing can be checked locally, but
GitHub-hosted execution is needed to verify a new trigger end to end.

## Failed or interrupted uploads

Duplicate uploads fail loudly (`skip-existing` is disabled). PyPI uploads are
not atomic: a failure may leave only one file published. Inspect the index and
the run's retained artefact before retrying. Never move a release tag or rebuild
different bytes to replace published files. Uploaded filenames cannot be reused,
even after deletion; corrections normally need a new version and tag.
The validated distributions are retained as a GitHub Actions artefact for seven
days. Re-running only the failed publish job reuses the existing build output
while it remains available; it still fails on files already present.
