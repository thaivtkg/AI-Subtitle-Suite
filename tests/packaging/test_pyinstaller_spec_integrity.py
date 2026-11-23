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

    # Đảm bảo đã loại bỏ hoàn toàn CAT Studio / QML / llama_cpp
    assert "qml_translation" not in content, "datas không được còn 'ui/qml_translation'"
    assert "llama_cpp" not in content, "spec không được còn phụ thuộc 'llama_cpp'"
    assert "core.translation" not in content, "hiddenimports không được còn 'core.translation'"

    # Kiểm tra hiddenimports cốt lõi vẫn còn
    assert "'core.subtitle_generation'" in content or '"core.subtitle_generation"' in content, (
        "hiddenimports phải chứa module 'core.subtitle_generation'"
    )
