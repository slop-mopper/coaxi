# Releasing coaxi

The manual workflow is `.github/workflows/release.yml`, displayed as
**Publish Python package** in GitHub Actions. It defaults to **test-pypi**.
It never uploads on a push, pull request, tag push or GitHub Release event.
Running it manually against a matching version tag authorises a real upload
to the selected index, subject to the environment's protection rules.

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

## Prepare and rehearse 1.0.0

1. Review and commit the release files. Ensure `pyproject.toml` and the `coaxi`
   entry in `uv.lock` both say `1.0.0`; run the usual checks.
2. Push that commit to the repository. Create an annotated tag at the reviewed
   commit and push only that tag:

   ```sh
   git tag -a v1.0.0 -m "coaxi 1.0.0"
   git push origin v1.0.0
   ```

3. Open **Actions → Publish Python package → Run workflow**.
   Select the **`v1.0.0` tag as the workflow ref**, not `master`, and choose
   destination **`test-pypi`**. If the UI does not offer tags, use GitHub CLI:

   ```sh
   gh workflow run release.yml --ref v1.0.0 -f destination=test-pypi
   ```

   This is an actual TestPyPI upload, not a dry run.
4. Review the run, distribution hashes, TestPyPI page, rendered README and files.
   Test installation outside the checkout. One way to keep runtime dependencies
   on production PyPI is to download the **specific wheel** from the TestPyPI
   release's Files tab, check its SHA-256 against the workflow's log, and use:

   ```sh
   uv venv --python 3.13 /tmp/coaxi-release-consumer
   uv pip install --python /tmp/coaxi-release-consumer/bin/python \
     --index-url https://pypi.org/simple/ /absolute/path/to/coaxi-1.0.0-py3-none-any.whl
   /tmp/coaxi-release-consumer/bin/python -I -c \
     'import coaxi; from importlib.metadata import version; print(version("coaxi"), coaxi.__file__)'
   ```

   Use a fresh destination directory for the consumer. Avoid adding TestPyPI as
   an extra dependency index: it need not contain the runtime dependency graph.

## Publish to PyPI

Run the same workflow against **`v1.0.0`**, selecting **`pypi`**, after the
rehearsal succeeds. Review and approve the `pypi` deployment if required.
Check <https://pypi.org/project/coaxi/1.0.0/> and install `coaxi==1.0.0` from
production PyPI in another fresh consumer environment.

Each run validates and publishes its own exact pair of files. Separate TestPyPI
and PyPI runs rebuild from the same tag; they are not byte-for-byte artefact
promotion, and isolated build dependencies are not pinned by `uv.lock`.

## What the workflow checks

- The full Git ref must equal `refs/tags/v` plus the static project version.
  Branches and mismatched tags fail; the project and lockfile must agree.
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

No workflow run has been performed merely by adding these files. GitHub's OIDC
exchange, environment approvals, Ubuntu package installation and real index
uploads require a GitHub-hosted rehearsal; local checks cannot prove those.

## Failed or interrupted uploads

Duplicate uploads fail loudly (`skip-existing` is disabled). PyPI uploads are
not atomic: a failure may leave only one file published. Inspect the index and
the run's retained artefact before retrying. Never move a release tag or rebuild
different bytes to replace published files. Uploaded filenames cannot be reused,
even after deletion; corrections normally need a new version and tag.
The validated distributions are retained as a GitHub Actions artefact for seven
days. Re-running only the failed publish job reuses the existing build output
while it remains available; it still fails on files already present.
