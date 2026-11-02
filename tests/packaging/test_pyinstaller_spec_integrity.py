# -*- coding: utf-8 -*-
import os
import ast
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def test_spec_file_naming_and_legacy_cleanup():
    """Tệp spec mới phải là 'AI Subtitle Suite.spec', tệp cũ phải được dọn dẹp."""
    new_spec = os.path.join(PROJECT_ROOT, "AI Subtitle Suite.spec")
    old_spec = os.path.join(PROJECT_ROOT, "AI Subtitle Studio.spec")

    assert os.path.exists(new_spec), "Tệp 'AI Subtitle Suite.spec' phải tồn tại ở thư mục gốc"
    assert not os.path.exists(old_spec), "Tệp cũ 'AI Subtitle Studio.spec' phải được xóa bỏ"


def test_spec_ast_syntax_and_configuration():
    """Tệp spec mới phải có cú pháp Python hợp lệ và đầy đủ cấu hình cho QML & llama-cpp."""
    spec_path = os.path.join(PROJECT_ROOT, "AI Subtitle Suite.spec")
    if not os.path.exists(spec_path):
        pytest.fail("AI Subtitle Suite.spec không tồn tại")

    with open(spec_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Kiểm tra cú pháp AST hợp lệ
    parsed = ast.parse(content)
    assert parsed is not None

    # Kiểm tra tên ứng dụng trong EXE và COLLECT
    assert "name='AI Subtitle Suite'" in content or 'name="AI Subtitle Suite"' in content, (
        "Tên ứng dụng trong EXE/COLLECT phải là 'AI Subtitle Suite'"
    )
    assert "AI Subtitle Studio" not in content, (
        "Không được còn tàn dư chuỗi 'AI Subtitle Studio' trong file spec"
    )

    # Kiểm tra cấu hình QML datas
    assert "qml_translation" in content, "datas phải bao gồm thư mục 'ui/qml_translation'"

    # Kiểm tra cấu hình llama_cpp datas & dynamic libs
    assert "collect_data_files('llama_cpp')" in content or 'collect_data_files("llama_cpp")' in content, (
        "datas phải thu thập data files của llama_cpp"
    )
    assert "collect_dynamic_libs('llama_cpp')" in content or 'collect_dynamic_libs("llama_cpp")' in content, (
        "binaries phải thu thập dynamic libraries của llama_cpp"
    )

    # Kiểm tra hiddenimports
    for mod in [
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuickControls2",
        "llama_cpp",
        "core.translation",
        "core.subtitle_generation",
    ]:
        assert f"'{mod}'" in content or f'"{mod}"' in content, (
            f"hiddenimports phải chứa module '{mod}'"
        )
