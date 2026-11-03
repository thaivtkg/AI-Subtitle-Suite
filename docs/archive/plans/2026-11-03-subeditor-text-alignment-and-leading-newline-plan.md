# Kế hoạch Kỹ thuật: Khắc phục Lệch Vị trí Phụ đề (Sát Khung) trong SubEditor

> **Mã Kế hoạch:** `PLAN-SUBEDITOR-ALIGNMENT-AND-SANITIZATION-001`  
> **Người lập:** Senior QA Lead / Software Quality Architect  
> **Tiêu chuẩn Kỹ thuật:** Ponytail Senior Dev Mode (Xử lý triệt để tại tầng dùng chung, diff tối thiểu, TDD 100% Green, không sinh boilerplate).  
> **Thời gian:** 2026-11-03  
> **Trạng thái:** Sẵn sàng chuyển giao cho Developer triển khai  

---

## 1. Bối cảnh & Nghiệm thu Báo cáo Developer

### 1.1. Nghiệm thu Kế hoạch `PLAN-CAT-PROGRESS-AND-OUTPUT-STABILITY-001`
- Developer đã hoàn tất xuất sắc toàn bộ 4 tác vụ của kế hoạch trước (Commits [`4f1c08a`](file:///d:/ai-subtitle-suite/) và [`1c0ecc3`](file:///d:/ai-subtitle-suite/)):
  - Khử triệt để đường dẫn rác pytest trong `%LOCALAPPDATA%/AI Subtitle Suite/settings.json` và bổ sung Regex Guard tại [`ui/Gui.py:2790-2830`](file:///d:/ai-subtitle-suite/ui/Gui.py#L2790-L2830).
  - Đóng thẻ `<think>\n</think>\n` cho DeepSeek-R1 tại [`core/translation/core/prompt_builder.py:136`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py#L136).
  - Dải bò tiến độ $95\% \rightarrow 98\%$ và Watchdog 90s tại [`core/translation/controllers/translation_controller.py`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py).
  - 31/31 bài test tự động đạt 100% Green.
- **Xác nhận nghiệm thu:** ĐẠT YÊU CẦU.

---

## 2. Phân tích Nguyên nhân Gốc rễ: "Sub trong editor bị lệch sát khung thay vì vị trí như sub bên dưới"

Người dùng gửi ảnh chụp màn hình thực tế (kích thước $1024 \times 94$ pixel) kèm mô tả lỗi:
- **Dòng trên (Câu #23):** `"Em cảm ơn ngài"` nằm trên nền tối không chọn `RGB(21, 26, 39)`.
- **Dòng dưới (Câu #24):** `"|Thứ này hợp với nàng hơn cái kia nhiều đấy."` nằm trên nền tím chọn `RGB(59, 62, 136)`.

### 2.1. Phân tích Tọa độ Pixel thực tế
- **Dòng dưới (Câu #24):** Chiều cao hàng là $43\text{px}$ ($y = 47 \rightarrow 89$). Chữ nằm ở $y = 65 \rightarrow 75$, căn giữa hoàn hảo theo chiều dọc (khoảng cách trên $18\text{px}$, khoảng cách dưới $14\text{px}$).
- **Dòng trên (Câu #23):** Chiều cao hàng là $46\text{px}$ ($y = 0 \rightarrow 45$). Toàn bộ khoảng trên từ $y = 0 \rightarrow 33$ ($34\text{px}$) là khoảng trống rỗng hoàn toàn! Chữ `"Em cảm ơn ngài"` bị **dồn ép xuống đáy cell ở tọa độ $y = 34 \rightarrow 41$**, cách mép đáy chỉ vỏn vẹn $4\text{px}$!

### 2.2. Điểm lỗi trong mã nguồn
1. **Lỗ hổng phân tích SRT tại [`core/export/subtitle_parser.py:25`](file:///d:/ai-subtitle-suite/core/export/subtitle_parser.py#L25):**
   ```python
   def parse_srt_content(content: str) -> list[dict]:
       ...
       segments.append({
           "id": uuid.uuid4().hex,
           "stt": str(len(segments) + 1),
           "start": _to_ms(start), "end": _to_ms(end),
           "text": "\n".join(lines[2:]), # KHÔNG CÓ .strip()!
           "status": "draft",
           "metadata": {"type": "normal"},
       })
   ```
   Trong tệp SRT thực tế của dự án ([`D:/Projects/JMSZ.ai-subtitle/artifacts/timing/JMSZ_timing.srt:89-93`](file:///D:/Projects/JMSZ.ai-subtitle/artifacts/timing/JMSZ_timing.srt#L89-L93)):
   ```srt
   23
   00:02:05,450 --> 00:02:07,110

   Em cảm ơn ngài
   ```
   Dòng 91 là một **dòng trống (blank line)** ngay sau mốc thời gian. Do `subtitle_parser.py` chỉ dùng `"\n".join(lines[2:])` mà không gọi `.strip()`, nội dung phụ đề của câu 23 trở thành `"\nEm cảm ơn ngài"` (chứa ký tự xuống dòng `\n` ở đầu câu).

2. **Dựng giao diện Table không làm sạch chuỗi tại [`ui/SubEditor.py:837`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L837):**
   ```python
   display_text = seg['text'] if seg['text'].strip() else "[ Chưa có nội dung ]"
   text_item = QTableWidgetItem(display_text)
   ```
   `display_text` lấy trực tiếp `seg['text']` (vẫn còn `\n` ở đầu). `QTableWidgetItem` coi dòng đầu tiên là chuỗi rỗng và hiển thị `"Em cảm ơn ngài"` ở dòng thứ 2, đẩy chữ tụt xuống sát đáy khung cell.

3. **Thiếu căn lề dọc chuẩn (`Qt.AlignVCenter`) cho cột nội dung:**
   Các cột STT, Start, End, Duration đều được gán `Qt.AlignCenter`, trong khi cột `COL_TEXT` không được thiết lập tường minh `setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)`.

4. **Thiếu padding nội dung cell trong CSS Liquid Theme:**
   Tại [`ui/core/liquid_theme_engine.py:784-787`](file:///d:/ai-subtitle-suite/ui/core/liquid_theme_engine.py#L784-L787):
   ```css
   QTableWidget::item, QTableView::item {
       outline: none;
       border: none;
       /* Thiếu padding ngang/dọc */
   }
   ```
   Làm chữ phụ đề không có khoảng đệm an toàn, dính sát viền khi co giãn.

---

## 3. Các Tác vụ Kỹ thuật Triển khai (Developer Action Items)

### Tác vụ 1: Làm sạch dữ liệu phụ đề khi bóc tách SRT (Root Cause Fix)
- **Vị trí can thiệp:** [`core/export/subtitle_parser.py:25`](file:///d:/ai-subtitle-suite/core/export/subtitle_parser.py#L25)
- **Nội dung thực hiện:**
  Thêm `.strip()` vào kết quả ghép dòng phụ đề:
  ```python
  "text": "\n".join(lines[2:]).strip(),
  ```
  Đảm bảo mọi dòng trống vô tình xuất hiện trước/sau phụ đề trong file SRT đều bị triệt tiêu ngay khi nạp vào RAM.

### Tác vụ 2: Chuẩn hóa hiển thị và Căn giữa theo chiều dọc trong SubEditor Table
- **Vị trí can thiệp:** [`ui/SubEditor.py:837-856`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L837-L856)
- **Nội dung thực hiện:**
  Làm sạch chuỗi hiển thị và thiết lập căn giữa dọc cho `text_item`:
  ```python
  clean_text = str(seg.get('text', '')).strip()
  display_text = clean_text if clean_text else "[ Chưa có nội dung ]"
  text_item = QTableWidgetItem(display_text)
  text_item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
  ```

### Tác vụ 3: Đồng bộ làm sạch dữ liệu trong CurrentSubtitleEditor
- **Vị trí can thiệp:** [`ui/SubEditor.py:211`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L211)
- **Nội dung thực hiện:**
  Trong hàm `CurrentSubtitleEditor.set_values()`:
  ```python
  target_text = str(text or "").strip()
  ```
  Ngăn chặn việc gán chuỗi có `\n` ở đầu vào `QTextEdit` làm con trỏ văn bản và chữ bị đẩy xuống dòng 2 của ô soạn thảo.

### Tác vụ 4: Bổ sung Padding cho QTableWidget Item trong Liquid Theme Engine
- **Vị trí can thiệp:** [`ui/core/liquid_theme_engine.py:784-787`](file:///d:/ai-subtitle-suite/ui/core/liquid_theme_engine.py#L784-L787)
- **Nội dung thực hiện:**
  Bổ sung khoảng đệm tiêu chuẩn cho các cell trong bảng:
  ```css
  QTableWidget::item, QTableView::item {
      outline: none;
      border: none;
      padding: 4px 8px;
  }
  ```

### Tác vụ 5: Viết bài kiểm thử TDD tự động bảo vệ
- **Vị trí file mới:** `tests/ui/test_subeditor_text_alignment.py`
- **Các ca kiểm thử bắt buộc:**
  1. `test_parse_srt_content_strips_leading_newlines()`: Kiểm tra SRT có dòng trống trước câu phụ đề (như câu 23 trong `JMSZ_timing.srt`) được chuẩn hóa thành chuỗi không chứa `\n` ở đầu.
  2. `test_subeditor_table_item_vertical_alignment_and_stripped_text()`: Nạp đoạn phụ đề chứa khoảng trắng/ký tự xuống dòng đầu câu vào `SubtitleEditorWidget`, kiểm tra `text_item.text()` không có dòng trống và `text_item.textAlignment()` có cờ `Qt.AlignVCenter`.
  3. `test_current_subtitle_editor_strips_text_on_set_values()`: Kiểm tra `CurrentSubtitleEditor.text_edit.toPlainText()` không chứa ký tự xuống dòng thừa ở đầu.

---

## 4. Tiêu chí Nghiệm thu (Definition of Done - DoD)

1. **Khắc phục triệt để hình ảnh:** Hàng #23 và Hàng #24 trong `SubEditor` có cùng một tọa độ lề trên/dưới đồng nhất, chữ phụ đề nằm ngay ngắn ở vị trí giữa hàng (`Qt.AlignVCenter`), không bị dồn sát đáy mép khung.
2. **Không làm hỏng phụ đề nhiều dòng hợp lệ:** Nếu phụ đề có 2 dòng thoại thực tế (ví dụ: `"- Chào anh\n- Chào em"`), chỉ xóa các ký tự xuống dòng rỗng ở đầu và cuối chuỗi, giữ nguyên ngắt dòng bên trong.
3. **100% Green Test Suite:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/ui/test_subeditor_text_alignment.py tests/core/test_editor_ui.py -v
   ```
   Tất cả bài test mới và cũ đều pass mà không gây lỗi hồi quy.
