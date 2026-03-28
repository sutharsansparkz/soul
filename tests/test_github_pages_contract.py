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
    hero_source = (ROOT / "site" / "src" / "components" / "HeroSection.tsx").read_text(encoding="utf-8")
    navbar_source = (ROOT / "site" / "src" / "components" / "NavBar.tsx").read_text(encoding="utf-8")
    footer_source = (ROOT / "site" / "src" / "components" / "SiteFooter.tsx").read_text(encoding="utf-8")
    repo_hook = (ROOT / "site" / "src" / "hooks" / "useRepoSnapshot.ts").read_text(encoding="utf-8")
    entrypoint = (ROOT / "site" / "src" / "main.tsx").read_text(encoding="utf-8")
    combined_source = "\n".join((app_source, hero_source, navbar_source, footer_source, repo_hook))

    assert "<title>SOUL | Terminal-first AI Companion</title>" in index_html
    assert '<div id="root"></div>' in index_html
    assert '/src/main.tsx' in index_html
    assert 'href="/logo.png"' in index_html
    assert "persistent companion that lives in your terminal".lower() in hero_source.lower()
    assert 'const GITHUB_REPOSITORY = "sparkz-technology/soul"' in repo_hook
    assert 'export const GITHUB_REPOSITORY_URL = `https://github.com/${GITHUB_REPOSITORY}`' in repo_hook
    assert "https://api.github.com/repos/" in repo_hook
    assert "/tree/main/docs" in navbar_source
    assert 'src="/logo.png"' in navbar_source
    assert 'src="/logo.png"' in footer_source
    assert "repo-header-pill" in navbar_source
    assert "mobile-menu-button" in navbar_source
    assert "mobile-menu-panel" in navbar_source
    assert "stargazers" in navbar_source
    assert "Contributors {repoSnapshot.contributorCount}:" in footer_source
    assert "Contributors" in footer_source
    assert "import './index.css';" in entrypoint


def test_pages_site_support_files_exist():
    assert (ROOT / "site" / "src" / "index.css").exists()
    assert (ROOT / "site" / "public" / "404.html").exists()
    assert (ROOT / "site" / "public" / ".nojekyll").exists()
    assert (ROOT / "site" / "public" / "logo.png").exists()


def test_site_component_files_stay_under_250_lines():
    files = [
        ROOT / "site" / "src" / "App.tsx",
        *(ROOT / "site" / "src" / "components").glob("*.tsx"),
    ]

    for path in files:
        assert sum(1 for _ in path.open(encoding="utf-8")) <= 250, f"{path.name} exceeds 250 lines"
