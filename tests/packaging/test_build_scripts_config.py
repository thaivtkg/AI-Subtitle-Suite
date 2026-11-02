# -*- coding: utf-8 -*-
import os
import re

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_build_py_targets_suite_spec():
    """build.py phai tro den 'AI Subtitle Suite.spec' va ten goi AI Subtitle Suite."""
    build_py_path = os.path.join(PROJECT_ROOT, "build.py")
    assert os.path.exists(build_py_path), "build.py phai ton tai"
    with open(build_py_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "AI Subtitle Suite.spec" in content, "build.py phai tro vao AI Subtitle Suite.spec"
    assert "AI Subtitle Studio.spec" not in content, "build.py khong duoc chua ten spec cu"
    assert "--name=AI Subtitle Suite" in content, "build.py fallback phai la AI Subtitle Suite"


def test_installer_iss_uses_suite_branding():
    """installer.iss phai dinh nghia dung cac thong so cua AI Subtitle Suite."""
    iss_path = os.path.join(PROJECT_ROOT, "installer.iss")
    assert os.path.exists(iss_path), "installer.iss phai ton tai"
    with open(iss_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "AppName=AI Subtitle Suite" in content
    assert r"DefaultDirName={autopf}\AI Subtitle Suite" in content
    assert r"UninstallDisplayIcon={app}\AI Subtitle Suite.exe" in content
    assert "OutputBaseFilename=AI_Subtitle_Suite_Setup_v1.0.0" in content
    assert r'Source: "dist\AI Subtitle Suite\*"' in content
    assert r'Filename: "{app}\AI Subtitle Suite.exe"' in content
    assert "AI Subtitle Studio" not in content, "installer.iss khong duoc chua ten cu Studio"


def test_deployment_setup_iss_uses_suite_branding():
    """deployment/installer/setup.iss phai dong bo voi AI Subtitle Suite."""
    iss_path = os.path.join(PROJECT_ROOT, "deployment", "installer", "setup.iss")
    if os.path.exists(iss_path):
        with open(iss_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert '#define MyAppName "AI Subtitle Suite"' in content
        assert '#define MyAppExeName "AI Subtitle Suite.exe"' in content
        assert "AISubtitleSuite_Setup_v" in content or "AI_Subtitle_Suite_Setup_v" in content


def test_readme_packaging_commands_updated():
    """README.md phai huong dan dong goi voi AI Subtitle Suite.spec."""
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    assert os.path.exists(readme_path), "README.md phai ton tai"
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'pyinstaller --noconfirm --clean "AI Subtitle Suite.spec"' in content
    assert "AI Subtitle Studio.spec" not in content
