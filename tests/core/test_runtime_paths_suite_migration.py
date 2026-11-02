# -*- coding: utf-8 -*-
import os
import shutil
from pathlib import Path
import pytest
from core.runtime.runtime_paths import RuntimePaths


def test_runtime_paths_app_name():
    """RuntimePaths.APP_NAME phai la 'AI Subtitle Suite'."""
    assert RuntimePaths.APP_NAME == "AI Subtitle Suite"
    assert RuntimePaths.get_user_data_dir().name == "AI Subtitle Suite"


def test_legacy_user_data_migration(tmp_path, monkeypatch):
    """ensure_user_data_dirs() phai ke thua an toan du lieu cu tu AI Subtitle Studio."""
    fake_localappdata = tmp_path / "localappdata"
    fake_localappdata.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    # Tao du lieu gia o thu muc cu AI Subtitle Studio
    legacy_dir = fake_localappdata / "AI Subtitle Studio"
    legacy_dir.mkdir()
    (legacy_dir / "settings.json").write_text('{"theme": "dark"}', encoding="utf-8")
    (legacy_dir / "glossary.db").write_text("GLOSSARY_DATA", encoding="utf-8")
    (legacy_dir / "tm.db").write_text("TM_DATA", encoding="utf-8")
    legacy_models = legacy_dir / "models"
    legacy_models.mkdir()
    (legacy_models / "gemma_2b.gguf").write_text("MODEL_BINARY", encoding="utf-8")

    # Thu muc moi AI Subtitle Suite chua ton tai
    suite_dir = fake_localappdata / "AI Subtitle Suite"
    assert not suite_dir.exists()

    # Thuc thi khoi tao thu muc
    RuntimePaths.ensure_user_data_dirs()

    # Kiem tra da di tru an toan sang thu muc moi
    assert suite_dir.exists()
    assert (suite_dir / "settings.json").read_text(encoding="utf-8") == '{"theme": "dark"}'
    assert (suite_dir / "glossary.db").read_text(encoding="utf-8") == "GLOSSARY_DATA"
    assert (suite_dir / "tm.db").read_text(encoding="utf-8") == "TM_DATA"
    assert (suite_dir / "models" / "gemma_2b.gguf").read_text(encoding="utf-8") == "MODEL_BINARY"


def test_branding_in_source_files():
    """Cac thanh phan UI va entry point phai dong bo thuong hieu AI Subtitle Suite."""
    project_root = Path(__file__).resolve().parent.parent.parent

    # 1. main.py
    main_py = (project_root / "main.py").read_text(encoding="utf-8")
    assert "aisubtitlesuite" in main_py

    # 2. ui/Gui.py
    gui_py = (project_root / "ui" / "Gui.py").read_text(encoding="utf-8")
    assert 'self.setWindowTitle("AI Subtitle Suite")' in gui_py

    # 3. AppHeader.qml
    app_header_qml = (project_root / "ui" / "qml_translation" / "components" / "AppHeader.qml").read_text(encoding="utf-8")
    assert "AI Subtitle Suite" in app_header_qml

    # 4. StudioLaunchpad.qml
    launchpad_qml = (project_root / "ui" / "qml_translation" / "components" / "StudioLaunchpad.qml").read_text(encoding="utf-8")
    assert 'text: "AI Subtitle Suite"' in launchpad_qml
