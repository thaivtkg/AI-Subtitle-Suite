# Kế hoạch Triển khai: Đổi tên & Nâng cấp File PyInstaller Spec (`AI Subtitle Suite.spec`) và Đồng bộ Định danh Dự án (PLAN-PACKAGING-SPEC-BRANDING-001)

> **Dành cho Developer thực thi:** BẮT BUỘC thực hiện từng tác vụ tuần tự theo chuẩn Test-Driven Development (TDD). Các bước sử dụng cú pháp checkbox (`- [ ]`) để theo dõi tiến độ. Tuyệt đối không nhảy cóc các bước kiểm thử. Không tự ý sửa đổi logic nghiệp vụ ngoài phạm vi đóng gói và định danh dự án.

**Mục tiêu:**
1. Đổi tên tệp đặc tả PyInstaller `AI Subtitle Studio.spec` thành `AI Subtitle Suite.spec`, đồng bộ tên tệp thực thi kết xuất (`AI Subtitle Suite.exe`) và thư mục kết xuất (`dist/AI Subtitle Suite/`).
2. Bổ sung các thành phần đóng gói bị thiếu trong kiến trúc mới của **AI Subtitle Suite**:
   - Thư mục giao diện dịch thuật QML (`ui/qml_translation/`) và các module `PySide6.QtQuick`, `PySide6.QtQuickWidgets`, `PySide6.QtQml`, `PySide6.QtQuickControls2`.
   - Dynamic libraries (`llama.dll`, ggml backends), dữ liệu và hidden imports của bộ dịch lõi `llama_cpp`.
   - Các gói module nội bộ mới (`core.translation`, `core.subtitle_generation`, `core.database`).
3. Cập nhật các kịch bản build và đóng gói installer: `build.py`, `installer.iss`, `deployment/installer/setup.iss`, `README.md`.
4. Cập nhật định danh ứng dụng (App Branding):
   - Tiêu đề cửa sổ chính `MainWindow`: `"AI Subtitle Suite"`.
   - Tiêu đề QML header: `"⚡ AI Subtitle Suite"`.
   - Taskbar AppUserModelID: `'aisubtitlesuite.v1.0'`.
   - `RuntimePaths.APP_NAME = "AI Subtitle Suite"` kèm cơ chế kế thừa dữ liệu cũ (Legacy Migration Guard) từ `AI Subtitle Studio` để bảo toàn Model, Glossary và Translation Memory của người dùng.

---

## Các ràng buộc toàn cục (Global Constraints)
* **Bảo toàn Dữ liệu Người dùng (Zero Data Loss):** Khi nâng cấp `APP_NAME` thành `"AI Subtitle Suite"`, hệ thống phải có cơ chế fallback thông minh: nếu thư mục mới `%LOCALAPPDATA%\AI Subtitle Suite` chưa có dữ liệu mà thư mục cũ `%LOCALAPPDATA%\AI Subtitle Studio` tồn tại, tự động kế thừa `models/`, `glossary.db`, `tm.db`, và `settings.json`.
* **Toàn vẹn Binary Đóng gói (Packaging Integrity):** Tệp `.spec` mới phải đóng gói đầy đủ cả 2 phân hệ: Phân hệ Biên tập Phụ đề (Whisper + VAD + FFmpeg) và Phân hệ Dịch thuật CAT Studio (QML + llama-cpp GGUF), không bị lỗi thiếu DLL hay thiếu QML khi chạy `.exe` độc lập.
* **Zero Regression:** Toàn bộ 38 test specs hiện hành của hệ thống phải tiếp tục duy trì trạng thái 100% Green.

---

## Cấu trúc các tác vụ (Tasks Breakdown)

### Tác vụ 1: Nâng cấp và Đổi tên Tệp PyInstaller Spec (`AI Subtitle Suite.spec`)
**Files:**
* Tạo mới: `AI Subtitle Suite.spec` (thay thế và xóa `AI Subtitle Studio.spec`)
* Sửa đổi / Dọn dẹp: `deployment/build/ai_subtitle_studio.spec` -> `deployment/build/ai_subtitle_suite.spec`
* Kiểm thử: `tests/packaging/test_pyinstaller_spec_integrity.py`

- [x] **Bước 1.1: Viết test kiểm thử cấu trúc và tính toàn vẹn của file spec**
  Tạo `tests/packaging/test_pyinstaller_spec_integrity.py`:
  - Kiểm tra file `AI Subtitle Suite.spec` tồn tại ở thư mục gốc.
  - File cũ `AI Subtitle Studio.spec` không còn tồn tại.
  - Đọc nội dung spec và xác nhận:
    - `name='AI Subtitle Suite'` trong cả `EXE` và `COLLECT`.
    - `datas` có chứa đường dẫn tới `ui/qml_translation` và `llama_cpp`.
    - `binaries` có chứa dynamic libs của `llama_cpp` và `ctranslate2`.
    - `hiddenimports` có chứa `PySide6.QtQuick`, `PySide6.QtQuickWidgets`, `PySide6.QtQml`, `llama_cpp`.
- [x] **Bước 1.2: Chạy test để xác nhận test thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/packaging/test_pyinstaller_spec_integrity.py -v`.
- [x] **Bước 1.3: Khởi tạo `AI Subtitle Suite.spec` với đầy đủ cấu hình mới**
  - Đổi tên tệp và cập nhật:
    ```python
    # 1. Thu thập data & dynamic libs
    datas = []
    datas += collect_data_files('faster_whisper')
    datas += collect_data_files('ctranslate2')
    datas += collect_data_files('huggingface_hub')
    datas += collect_data_files('tokenizers')
    datas += collect_data_files('llama_cpp')

    # QML translation studio
    qml_dir = os.path.join(project_root, 'ui', 'qml_translation')
    if os.path.exists(qml_dir):
        datas.append((qml_dir, os.path.join('ui', 'qml_translation')))

    # Resources & FFmpeg
    ...
    binaries = []
    binaries += collect_dynamic_libs('ctranslate2')
    binaries += collect_dynamic_libs('llama_cpp')

    # Hidden imports
    hiddenimports = [
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuickControls2',
        'faster_whisper',
        'ctranslate2',
        'llama_cpp',
        'huggingface_hub',
        'tokenizers',
        'torch',
        'torchaudio',
        'psutil',
        'sqlite3',
        'unittest.mock',
        'core',
        'core.translation',
        'core.subtitle_generation',
        'player',
        'ui',
        'workers',
    ]
    hiddenimports += collect_submodules('faster_whisper')
    hiddenimports += collect_submodules('ctranslate2')
    hiddenimports += collect_submodules('llama_cpp')
    ```
  - Cập nhật tên EXE và COLLECT thành `'AI Subtitle Suite'`.
  - Xóa file cũ `AI Subtitle Studio.spec`.
  - Đồng bộ `deployment/build/ai_subtitle_suite.spec` tương ứng.
- [x] **Bước 1.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/packaging/test_pyinstaller_spec_integrity.py -v`.
- [x] **Bước 1.5: Commit mã nguồn Tác vụ 1**
  `git commit -m "build: replace AI Subtitle Studio.spec with AI Subtitle Suite.spec supporting QML and llama-cpp (PLAN-PACKAGING-SPEC-BRANDING-001)"`

---

### Tác vụ 2: Cập nhật Kịch bản Đóng gói `build.py` & Inno Setup `installer.iss`
**Files:**
* Sửa đổi: `build.py`
* Sửa đổi: `installer.iss`
* Sửa đổi: `deployment/installer/setup.iss`
* Sửa đổi: `README.md`
* Kiểm thử: `tests/packaging/test_build_scripts_config.py`

- [x] **Bước 2.1: Viết test thất bại kiểm tra cấu hình build script**
  Tạo `tests/packaging/test_build_scripts_config.py`:
  - Xác nhận `build.py` trỏ vào `AI Subtitle Suite.spec`.
  - Xác nhận `installer.iss` cấu hình `AppName=AI Subtitle Suite`, file nguồn `dist\AI Subtitle Suite\*`, và output filename `AI_Subtitle_Suite_Setup_v1.0.0.exe`.
  - Xác nhận lệnh trong `README.md` sử dụng `AI Subtitle Suite.spec`.
- [x] **Bước 2.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/packaging/test_build_scripts_config.py -v`.
- [x] **Bước 2.3: Chỉnh sửa `build.py`, `installer.iss` và `README.md`**
  - Trong `build.py`:
    - Đổi banner: `"BAT DAU QUY TRINH DONG GOI AI SUBTITLE SUITE"`.
    - Đổi `spec_path = os.path.join(project_root, "AI Subtitle Suite.spec")`.
    - Đổi fallback `--name=AI Subtitle Suite`, thông báo xuất ra `dist/AI Subtitle Suite/`.
  - Trong `installer.iss`:
    - `AppName=AI Subtitle Suite`
    - `DefaultDirName={autopf}\AI Subtitle Suite`
    - `DefaultGroupName=AI Subtitle Suite`
    - `UninstallDisplayIcon={app}\AI Subtitle Suite.exe`
    - `OutputBaseFilename=AI_Subtitle_Suite_Setup_v1.0.0`
    - `Source: "dist\AI Subtitle Suite\*"`
    - `Filename: "{app}\AI Subtitle Suite.exe"`
  - Trong `README.md`: Cập nhật câu lệnh đóng gói `pyinstaller --noconfirm --clean "AI Subtitle Suite.spec"`.
- [x] **Bước 2.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/packaging/test_build_scripts_config.py -v`.
- [x] **Bước 2.5: Commit mã nguồn Tác vụ 2**
  `git commit -m "build: update build.py, installer scripts and docs to AI Subtitle Suite (PLAN-PACKAGING-SPEC-BRANDING-001)"`

---

### Tác vụ 3: Đồng bộ Định danh Ứng dụng & Bảo toàn Dữ liệu Người dùng (Legacy Migration)
**Files:**
* Sửa đổi: `core/runtime/runtime_paths.py`
* Sửa đổi: `ui/Gui.py:358`
* Sửa đổi: `main.py:72`
* Sửa đổi: `ui/qml_translation/components/AppHeader.qml:100`
* Sửa đổi: `ui/qml_translation/components/StudioLaunchpad.qml:127`
* Kiểm thử: `tests/core/test_runtime_paths_suite_migration.py`

- [x] **Bước 3.1: Viết test thất bại kiểm tra định danh ứng dụng và cơ chế kế thừa dữ liệu cũ**
  Tạo `tests/core/test_runtime_paths_suite_migration.py`:
  - Kiểm tra `RuntimePaths.APP_NAME == "AI Subtitle Suite"`.
  - Kiểm tra cơ chế `get_user_data_dir()`: Nếu thư mục `AI Subtitle Suite` chưa có nhưng `AI Subtitle Studio` có sẵn file `settings.json` hoặc thư mục `models/`, hệ thống hỗ trợ kế thừa hoặc tự động di chuyển an toàn mà không làm mất dữ liệu người dùng.
- [x] **Bước 3.2: Chạy test xác nhận thất bại**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/core/test_runtime_paths_suite_migration.py -v`.
- [x] **Bước 3.3: Triển khai cập nhật định danh và migration guard**
  - Trong `core/runtime/runtime_paths.py`:
    - Đặt `APP_NAME = "AI Subtitle Suite"`.
    - Trong `ensure_user_data_dirs()`: Thêm kiểm tra nếu thư mục mới trống và thư mục cũ `%LOCALAPPDATA%\AI Subtitle Studio` tồn tại, tự động sao chép hoặc trỏ mềm để giữ nguyên các model GGUF và cơ sở dữ liệu glossary/TM.
  - Trong `ui/Gui.py:358`: Đổi `self.setWindowTitle("AI Subtitle Suite")`.
  - Trong `main.py:72`: Đổi `myappid = 'aisubtitlesuite.v1.0'`.
  - Trong `ui/qml_translation/components/AppHeader.qml`: Đổi text hiển thị thành `"⚡ AI Subtitle Suite"`.
  - Trong `ui/qml_translation/components/StudioLaunchpad.qml`: Đổi text thành `"AI Subtitle Suite"`.
- [x] **Bước 3.4: Chạy lại test xác nhận PASS**
  Chạy `.\.venv\Scripts\python.exe -m pytest tests/core/test_runtime_paths_suite_migration.py -v`.
- [x] **Bước 3.5: Commit mã nguồn Tác vụ 3**
  `git commit -m "feat(branding): update app name to AI Subtitle Suite with legacy user data migration guard (PLAN-PACKAGING-SPEC-BRANDING-001)"`

---

### Tác vụ 4: Kiểm tra Cú pháp Spec bằng PyInstaller Dry-Run & Kiểm định Hồi quy Toàn diện
**Files:**
* Kiểm thử: Toàn bộ suite Desktop GUI Specs & Packaging Specs

- [x] **Bước 4.1: Kiểm tra tính hợp lệ cú pháp của tệp `.spec` mới**
  Chạy lệnh kiểm tra cú pháp Python trên `AI Subtitle Suite.spec`:
  ```powershell
  .\.venv\Scripts\python.exe -c "import ast; ast.parse(open('AI Subtitle Suite.spec', encoding='utf-8').read()); print('[OK] Spec syntax is valid')"
  ```
- [x] **Bước 4.2: Chạy kiểm định toàn bộ các bộ test hệ thống**
  ```powershell
  # 1. Bộ test packaging & build script
  .\.venv\Scripts\python.exe -m pytest tests/packaging/ tests/core/test_runtime_paths_suite_migration.py -v

  # 2. Bộ test ổn định luồng CAT Studio & Persistence Filter
  .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_workflow_stability.py tests/translation/test_cat_persistence_filter.py -v

  # 3. Bộ test cô lập tab dịch & UX dashboard
  .\.venv\Scripts\python.exe -m pytest tests/ui/test_translation_transfer_isolation.py tests/ui/test_recent_projects_ui.py -v

  # 4. Toàn bộ Desktop GUI Flow Specs (POM Triad)
  .\.venv\Scripts\python.exe -m pytest tests/gui/specs/ -v
  ```
- [x] **Bước 4.3: Commit hoàn tất kế hoạch**
  `git commit -m "chore: verify packaging spec dry-run and full regression suite (PLAN-PACKAGING-SPEC-BRANDING-001)"`
