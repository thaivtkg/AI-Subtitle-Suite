# Kế hoạch Kỹ thuật: Bổ sung Thẻ Chủ Ngữ & Nâng cấp Dịch thuật Anime TranslateGemma

> **Mã Kế hoạch:** `PLAN-CAT-SUBJECT-TAG-AND-GEMMA-ENHANCEMENT-001`  
> **Người lập:** Senior QA Lead / Software Quality Architect  
> **Tiêu chuẩn Kỹ thuật:** Ponytail Senior Dev Mode (Xử lý triệt để tại tầng dùng chung, diff tối thiểu, TDD 100% Green, không sinh boilerplate).  
> **Thời gian:** 2026-11-03  
> **Trạng thái:** Sẵn sàng chuyển giao cho Developer triển khai  

---

## 1. Nghiệm thu Báo cáo Developer & Bối cảnh

### 1.1. Nghiệm thu Kế hoạch `PLAN-SUBEDITOR-ALIGNMENT-AND-SANITIZATION-001`
- Developer đã hoàn tất xuất sắc toàn bộ 5 tác vụ (Commit [`ddf6149`](https://github.com/thaivtkg/AI-Subtitle-Suite/commit/ddf6149)):
  - Làm sạch `\n` ngầm trong SRT Parser [`core/export/subtitle_parser.py:15-55`](file:///d:/ai-subtitle-suite/core/export/subtitle_parser.py#L15-L55).
  - Căn giữa dọc `Qt.AlignVCenter` trong bảng [`ui/SubEditor.py:837-845`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L837-L845).
  - Làm sạch chuỗi cho ô `CurrentSubtitleEditor` [`ui/SubEditor.py:205-212`](file:///d:/ai-subtitle-suite/ui/SubEditor.py#L205-L212).
  - Bổ sung `padding: 4px 8px;` cho `QTableWidget::item` trong Liquid Theme [`ui/core/liquid_theme_engine.py:784-787`](file:///d:/ai-subtitle-suite/ui/core/liquid_theme_engine.py#L784-L787).
  - Bộ test hồi quy 24/24 specs đạt 100% Green.
- **Xác nhận nghiệm thu:** ĐẠT YÊU CẦU.

---

## 2. Phân tích Yêu cầu Mới & Nguyên nhân Gốc rễ

Người dùng phản ánh 2 vấn đề lớn trong CAT Studio đi kèm ảnh chụp thực tế:
1. **Muốn có Thẻ Chủ Ngữ trong câu:** Hiện tại dưới thanh CPS/CPL chỉ hiển thị các chip từ khóa `🏷️ [từ gốc] ➔ [nghĩa] 📌`, hoàn toàn thiếu vắng thẻ nhận diện chủ ngữ / đại từ xưng hô của câu thoại.
2. **Nâng cấp TranslateGemma dịch hội thoại Anime tự nhiên:**
   - Câu 1: `「この俺様に一体何の」`  
     Hiện tại TranslateGemma dịch bồi từng chữ và bóc tách ngô nghê:
     `🏷️ この俺様に ➔ đến tớ đây 📌` (sai hoàn toàn khẩu khí của `俺様`!), `🏷️ 一体 ➔ thì 📌`, `🏷️ 何の ➔ làm cái gì 📌`.  
     *Mong muốn:* `"Ngươi tìm ta đây rốt cuộc có chuyện gì?"`
   - Câu 2 (Nhân vật chính): `「そんなの決まってるわ。」`  
     Hiện tại TranslateGemma dịch máy móc nghĩa đen: *"Chuyện đó đã được quyết định rồi."*  
     *Mong muốn:* `"Chuyện đó còn phải hỏi sao!"` (hoặc *"Cái đó còn phải nói sao!"*).

### 2.1. Điểm nghẽn Kỹ thuật trong Mã Nguồn
1. **Tham số `active_pronoun_pair` bị bỏ rơi hoàn toàn tại [`core/translation/core/prompt_builder.py:15`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py#L15):**  
   Hàm `build_translation_prompt` nhận `active_pronoun_pair: str = ""` từ Controller, nhưng trong toàn bộ thân hàm **không có một dòng code nào đưa cặp ngôi xưng này vào System Prompt hoặc User Prompt**! Model LLM (TranslateGemma/Qwen) không nhận được bất kỳ chỉ dẫn nào về ngôi xưng nên tự đoán mò và chọn xưng "tớ - cậu" một cách ngẫu nhiên.
2. **Thiếu quy tắc dịch hội thoại Anime tiếng Nhật:**  
   Trong anime, nhân vật thường nói lửng câu (Ellipsis: `この俺様に一体何の[用だ]`) và lược bỏ chủ ngữ. Prompt hiện tại chỉ có 1 câu chung chung *"NATURAL DIALOGUE"*, không hướng dẫn model:
   - Nhận diện persona từ đại từ: `俺様 (oresama)` là kẻ ngạo mạn/trịch thượng ➔ bắt buộc xưng "ta / ta đây / bổn gia", gọi đối phương là "ngươi / các ngươi". TUYỆT ĐỐI KHÔNG dịch là "tớ" hay "mình".
   - Phục hồi chủ ngữ ẩn theo ngữ cảnh: Tự động bổ sung "Ngươi tìm ta đây..." để câu thoại tiếng Việt trôi chảy.
   - Dịch thoát nghĩa khẩu ngữ & đuôi câu: `そんなの決まってるわ` (đuôi khẳng định nữ tính `わ`) mang nghĩa "Chuyện đó còn phải hỏi sao!", không được dịch nghĩa đen của động từ `決まる` (quyết định).
3. **Quy định trích xuất `[TỪ GỐC]` bị buông lỏng:**  
   Prompt yêu cầu `list key original terms under '[TỪ GỐC]'` nhưng không có quy chuẩn cấm cắt vụn trợ từ/liên từ, dẫn đến model bóc tách thô thiển: `一体 ➔ thì`, `何の ➔ làm cái gì`.
4. **UI Workspace chưa có thẻ Chủ ngữ:**  
   Tại [`ui/qml_translation/components/TranslationWorkspace.qml:884-985`](file:///d:/ai-subtitle-suite/ui/qml_translation/components/TranslationWorkspace.qml#L884-L985), `termAlignmentFlow` chỉ lặp qua `currentAppliedTerms`. Chưa có chip đại diện cho **Chủ ngữ / Ngôi xưng hiện tại** của câu để người dùng theo dõi và thay đổi nhanh.

---

## 3. Các Tác vụ Kỹ thuật Triển khai (Developer Action Items)

### Tác vụ 1: Bộ nhận diện Chủ ngữ / Đại từ tiếng Nhật trong ContextAnalyzer
- **Vị trí can thiệp:** [`core/translation/core/context_analyzer.py`](file:///d:/ai-subtitle-suite/core/translation/core/context_analyzer.py)
- **Nội dung thực hiện:**
  Bổ sung hàm phân tích đại từ và ngữ khí câu thoại:
  ```python
  def detect_japanese_subject_pronoun(text: str) -> dict:
      """
      Nhận diện đại từ nhân xưng và khẩu khí anime trong câu tiếng Nhật.
      Trả về dict: {"subject": str, "pair": str, "tone": str}
      """
  ```
  - Quét đại từ ngôi 1 ngạo mạn: `俺様`, `おれさま`, `我` ➔ `{"subject": "Ta đây (俺様)", "pair": "Ta - Ngươi", "tone": "arrogant"}`.
  - Quét đại từ ngôi 2 đối địch/hạ thấp: `貴様`, `お前`, `あんた` ➔ gán đối phương là `"Ngươi"`.
  - Quét ngôi 1 khiêm nhường/nam tính: `僕`, `俺`, `私`, `あたし` ➔ gán cặp ngôi xưng phù hợp (`Tôi - Cậu`, `Tớ - Cậu`).
  - Quét đuôi câu nữ tính/khẳng định: `〜わ`, `〜わよ`, `〜かしら` ➔ nhận diện khẩu khí nữ giới.

### Tác vụ 2: Expose Thuộc tính & Thao tác Thẻ Chủ Ngữ trên TranslationController
- **Vị trí can thiệp:** [`core/translation/controllers/translation_controller.py`](file:///d:/ai-subtitle-suite/core/translation/controllers/translation_controller.py)
- **Nội dung thực hiện:**
  1. Thêm signal `currentSubjectTagChanged = Signal()`
  2. Bổ sung `@Property("QVariantMap", notify=currentSubjectTagChanged)`:
     `currentSubjectTag`: Trả về `{"text": "Ta - Ngươi", "source_pronoun": "俺様", "pair": "Ta - Ngươi", "is_detected": True}` khi chọn câu thoại có đại từ hoặc thừa kế từ `project_controller.activePronounPair`.
  3. Bổ sung `@Slot(str) def setSubjectPronoun(self, pronoun_pair: str)`: Cho phép người dùng bấm vào Thẻ Chủ Ngữ để chọn nhanh ngôi xưng mong muốn cho câu hoặc toàn bộ phân cảnh.

### Tác vụ 3: Tích hợp Thẻ Chủ Ngữ trên Giao diện TranslationWorkspace.qml
- **Vị trí can thiệp:** [`ui/qml_translation/components/TranslationWorkspace.qml:884-985`](file:///d:/ai-subtitle-suite/ui/qml_translation/components/TranslationWorkspace.qml#L884-L985)
- **Nội dung thực hiện:**
  Đặt một chip **Thẻ Chủ Ngữ (Subject Tag Chip)** nổi bật ở đầu dòng `termAlignmentFlow` (trước danh sách thuật ngữ):
  - Biểu tượng: `👤` hoặc `👑`.
  - Màu sắc: Tím Sapphire (`#8B5CF6`, nền trong suốt mờ `rgba(139, 92, 246, 0.18)`), phân biệt rõ với thẻ vàng `🏷️` của thuật ngữ thường.
  - Nhãn hiển thị: `👑 Chủ ngữ: Ta ➔ Ngươi` (hoặc đại từ phát hiện `👤 Ta đây (俺様)`).
  - Tương tác: Click mở Menu chọn nhanh các cặp ngôi xưng thông dụng trong Anime / Phim ảnh:
    - `Ta - Ngươi` (Chiến đấu / Ngạo mạn / Cổ trang)
    - `Tôi - Cậu` (Đồng trang lứa / Hiện đại)
    - `Tớ - Cậu` (Thanh xuân / Học đường)
    - `Anh - Em` (Lãng mạn)
    - `Em - Tiền bối` (Senpai - Kouhai)
    - `Tự do` (Theo ngữ cảnh)

### Tác vụ 4: Nâng cấp Prompt Dịch thuật Anime & TranslateGemma trong PromptBuilder
- **Vị trí can thiệp:** [`core/translation/core/prompt_builder.py:76-118`](file:///d:/ai-subtitle-suite/core/translation/core/prompt_builder.py#L76-L118)
- **Nội dung thực hiện:**
  1. **Áp dụng bắt buộc `active_pronoun_pair`:**
     Khi `active_pronoun_pair` có giá trị (ví dụ `"Ta - Ngươi"`), đưa quy tắc vào System Prompt:
     ```
     - MANDATORY PRONOUN PAIR: You MUST translate the dialogue using the pronoun relationship: '{active_pronoun_pair}' (First person: '{P1}', Second person: '{P2}').
     ```
  2. **Bổ sung Quy Tắc Bản Địa Hóa Hội Thoại Anime Tiếng Nhật:**
     Khi `source_lang == "Japanese"` hoặc `is_ja_origin`:
     - **Quy tắc Đại từ & Khẩu khí:** `俺様` bắt buộc dịch thành `"ta / ta đây / bổn gia"`, xưng hô với đối phương là `"ngươi"`. CẤM TUYỆT ĐỐI dịch là `"tớ"` hay `"mình"`.
     - **Phục hồi Chủ ngữ Ẩn (Implicit Subject Ellipsis):** Đối với các câu nói lửng (`この俺様に一体何の[用だ]`), model phải phục hồi chủ vị tự nhiên: `"Ngươi tìm ta đây rốt cuộc có chuyện gì?"`.
     - **Dịch Thoát Nghĩa Khẩu Ngữ & Đuôi Câu:** `そんなの決まってるわ` phải dịch thoát nghĩa thành `"Chuyện đó còn phải hỏi sao!"` hoặc `"Cái đó còn phải nói sao!"` (phản ánh ngữ khí dứt khoát của đuôi `わ`), KHÔNG dịch máy móc là `"đã được quyết định"`.
  3. **Chuẩn hóa Ràng Buộc Bóc Tách `[TỪ GỐC]`:**
     Chỉ trích xuất các từ/cụm từ có nghĩa ngữ cảnh độc lập (`この俺様 -> ta đây`, `一体 -> rốt cuộc`). Tuyệt đối KHÔNG cắt vụn ngữ pháp thành `"đến tớ đây"`, `"thì"`, `"làm cái gì"`.

### Tác vụ 5: Bộ Kiểm Thử TDD Bảo Vệ Tự Động
- **Vị trí file mới:** `tests/translation/test_cat_subject_tag_and_anime_gemma.py`
- **Các ca kiểm thử bắt buộc:**
  1. `test_detect_japanese_subject_pronoun_oresama()`: Câu chứa `俺様` nhận diện đúng cặp `"Ta - Ngươi"` và khẩu khí `"arrogant"`.
  2. `test_detect_japanese_sentence_ending_wa()`: Câu kết thúc bằng `わ` nhận diện đúng khẩu khí nữ tính khẳng định.
  3. `test_prompt_builder_injects_mandatory_pronoun_pair()`: `PromptBuilder.build()` đưa quy tắc đại từ bắt buộc vào prompt khi có `active_pronoun_pair`.
  4. `test_prompt_builder_japanese_anime_rules_present()`: Khi nguồn là Japanese, prompt chứa các quy tắc xử lý `俺様`, phục hồi câu lửng và dịch thoát nghĩa `決まってるわ`.
  5. `test_translation_controller_current_subject_tag_property()`: Kiểm tra `TranslationController.currentSubjectTag` phản hồi đúng khi chuyển câu và khi gọi `setSubjectPronoun`.

---

## 4. Tiêu chí Nghiệm thu (Definition of Done - DoD)

1. **Hiển thị Thẻ Chủ Ngữ trực quan:** Trong `TranslationWorkspace.qml`, xuất hiện Thẻ Chủ Ngữ `👑 Chủ ngữ: Ta ➔ Ngươi` ngay phía trên hoặc đầu dải từ gốc, bấm vào có thể đổi nhanh ngôi xưng.
2. **TranslateGemma dịch chuẩn ngữ cảnh Anime:**
   - `「この俺様に一体何の」` ➔ dịch tự nhiên: `"Ngươi tìm ta đây rốt cuộc có chuyện gì?"` (hoặc tương đương, đại từ "ta / ta đây - ngươi", không dịch là "tớ").
   - `「そんなの決まってるわ。」` ➔ dịch tự nhiên: `"Chuyện đó còn phải hỏi sao!"` (hoặc `"Cái đó còn phải nói sao!"`).
3. **Từ gốc không bị cắt vụn:** Không còn các chip ngô nghê `đến tớ đây`, `thì`, `làm cái gì`.
4. **100% Green Test Suite:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/translation/test_cat_subject_tag_and_anime_gemma.py tests/translation/test_context_prompt.py -v
   ```
   Tất cả bài test mới và cũ đều pass mà không gây lỗi hồi quy.
