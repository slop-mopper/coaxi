# test_documentation.py
# SPDX-License-Identifier: CC0-1.0
# This file was created by an AI model: openai/gpt-6.1-sol

"""Check the separation between documentation checks and Pages deployment."""

from pathlib import Path


def test_pages_workflow_permissions() -> None:
	"""Pull requests build without deployment credentials; only master can publish."""
	root = Path(__file__).resolve().parents[1]
	workflow = (root / ".github/workflows/docs.yml").read_text(encoding="utf-8")
	build, deploy = workflow.split("\n  deploy:\n", maxsplit=1)
	assert "\n  pull_request:\n    branches:\n      - master\n" in build
	assert "\n  push:\n    branches:\n      - master\n" in build
	assert "\n  workflow_dispatch:\n" in build
	assert "\npermissions: {}\n" in build
	assert "\n    permissions:\n      contents: read\n" in build
	assert "pages: write" not in build
	assert "id-token: write" not in build
	assert "pull_request_target" not in workflow
	assert "persist-credentials: false" in build
	assert "uv sync --locked --no-dev --group docs" in build
	assert "uv run --locked --no-dev --group docs sphinx-build -M html docs docs/_build -n -W --keep-going" in build
	guard = "if: github.ref == 'refs/heads/master' && github.event_name != 'pull_request'"
	upload = build.split("- name: Upload the Pages site\n", maxsplit=1)[1]
	assert guard in upload
	assert "uses: actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9" in upload
	assert "\n          name: github-pages\n          path: docs/_build/html\n" in upload
	assert guard in deploy
	assert "needs: build" in deploy
	assert "\n    permissions:\n      pages: write\n      id-token: write\n" in deploy
	assert "name: github-pages" in deploy
	assert "actions/checkout@" not in deploy
	assert "\n        run:" not in deploy
	assert deploy.count("uses:") == 1
	assert "uses: actions/deploy-pages@368f82528645a54fb793d4d04e342629a3f51346" in deploy
	assert "\n          artifact_name: github-pages\n" in deploy
