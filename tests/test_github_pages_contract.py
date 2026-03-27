from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_pages_workflow_exists_and_uses_official_actions():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "name: Deploy Pages" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "PAGES_DEPLOY_TOKEN" in workflow
    assert "enablement:" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "path: site" in workflow


def test_pages_site_has_core_project_content():
    index_html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")

    assert "<title>SOUL | Terminal-first AI Companion</title>" in index_html
    assert "persistent, mood-aware conversation from your terminal".lower() in index_html.lower()
    assert "https://github.com/sparkz-technology/soul" in index_html
    assert "https://github.com/sparkz-technology/soul/tree/main/docs" in index_html


def test_pages_site_support_files_exist():
    assert (ROOT / "site" / "styles.css").exists()
    assert (ROOT / "site" / "404.html").exists()
    assert (ROOT / "site" / ".nojekyll").exists()
