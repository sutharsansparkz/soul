from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_pages_workflow_exists_and_uses_official_actions():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "name: Deploy Pages" in workflow
    assert "actions/setup-node@v4" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "PAGES_DEPLOY_TOKEN" in workflow
    assert "enablement:" in workflow
    assert "npm ci" in workflow
    assert "npm run build" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow
    assert "path: site/dist" in workflow


def test_pages_site_has_core_project_content():
    index_html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    app_source = (ROOT / "site" / "src" / "App.tsx").read_text(encoding="utf-8")
    entrypoint = (ROOT / "site" / "src" / "main.tsx").read_text(encoding="utf-8")

    assert "<title>SOUL | Terminal-first AI Companion</title>" in index_html
    assert '<div id="root"></div>' in index_html
    assert '/src/main.tsx' in index_html
    assert "persistent companion that lives in your terminal".lower() in app_source.lower()
    assert "https://github.com/sparkz-technology/soul" in app_source
    assert "https://api.github.com/repos/" in app_source
    assert 'const GITHUB_REPOSITORY = "sparkz-technology/soul"' in app_source
    assert "/tree/main/docs" in app_source
    assert "Latest Release" in app_source
    assert "Contributors" in app_source
    assert "import './index.css';" in entrypoint


def test_pages_site_support_files_exist():
    assert (ROOT / "site" / "src" / "index.css").exists()
    assert (ROOT / "site" / "public" / "404.html").exists()
    assert (ROOT / "site" / "public" / ".nojekyll").exists()
