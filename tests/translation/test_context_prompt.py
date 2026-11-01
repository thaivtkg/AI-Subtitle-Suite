import unittest
from core.translation.core.prompt_builder import PromptBuilder

class TestPromptBuilder(unittest.TestCase):
    def test_prompt_format_chatml(self):
        """Kiểm tra xem PromptBuilder có xuất đúng cấu trúc ChatML và nội dung không"""
        story_summary = "Main character is a hero."
        prev_ctx = ["I am here."]
        current = "Where are you?"
        next_ctx = ["Come quick!"]
        
        prompt = PromptBuilder.build(
            story_summary, "English", "Vietnamese", prev_ctx, current, next_ctx
        )
        
        # 1. Xác thực cấu trúc ChatML
        self.assertIn("<|im_start|>system", prompt)
        self.assertIn("<|im_start|>user", prompt)
        self.assertIn("<|im_start|>assistant", prompt)
        
        # 2. Xác thực nội dung được tiêm đúng chỗ
        self.assertIn("STORY SUMMARY (CRITICAL CONTEXT):", prompt)
        self.assertIn("Main character is a hero.", prompt)
        self.assertIn("--- PREVIOUS SUBTITLES ---", prompt)
        self.assertIn("I am here.", prompt)
        self.assertIn("--- CURRENT SUBTITLE TO TRANSLATE ---", prompt)
        self.assertIn("Where are you?", prompt)
        
        # 3. Xác thực cờ Thinking OFF
        self.assertIn("DO NOT use reasoning", prompt)

    def test_prompt_format_gemma2_and_llama3(self):
        """Kiểm tra BUG-05: Định dạng prompt chuẩn theo dòng Gemma 2 và Llama 3."""
        # Gemma 2
        gemma_prompt = PromptBuilder.build(
            story_summary="Summary",
            current_sub="Hello world",
            model_family="gemma",
        )
        self.assertIn("<start_of_turn>user", gemma_prompt)
        self.assertIn("<end_of_turn>", gemma_prompt)
        self.assertIn("<start_of_turn>model", gemma_prompt)
        self.assertNotIn("<|im_start|>", gemma_prompt)

        # Llama 3
        llama_prompt = PromptBuilder.build(
            story_summary="Summary",
            current_sub="Hello world",
            model_family="llama",
        )
        self.assertIn("<|start_header_id|>system<|end_header_id|>", llama_prompt)
        self.assertIn("<|start_header_id|>user<|end_header_id|>", llama_prompt)
        self.assertIn("<|start_header_id|>assistant<|end_header_id|>", llama_prompt)
        self.assertNotIn("<|im_start|>", llama_prompt)

    def test_pronoun_pair_logic_01(self):
        """Kiểm tra Pure Model: Không còn bị ép đại từ xưng hô hay kính ngữ giả tạo."""
        prompt_ancient = PromptBuilder.build(
            story_summary="Phim kiếm hiệp cổ trang",
            current_sub="Ngươi đứng lại!",
            active_pronoun_pair="Ta - Ngươi",
            is_ja_origin=False,
        )
        self.assertNotIn("PRONOUN RELATIONSHIP", prompt_ancient)
        self.assertNotIn("tiền bối", prompt_ancient)
        self.assertNotIn("'em'", prompt_ancient)

        prompt_anime = PromptBuilder.build(
            story_summary="Anime học đường",
            current_sub="Chào anh!",
            active_pronoun_pair="Em - Tiền bối",
            is_ja_origin=True,
        )
        self.assertNotIn("PRONOUN RELATIONSHIP", prompt_anime)
        self.assertNotIn("JAPANESE TRANSLATION ARTIFACTS", prompt_anime)

    def test_cot_and_translation_prefix_logic_05_and_09(self):
        """Kiểm tra LOGIC-05 và LOGIC-09: Giữ nguyên bản dịch khi có 'Translation:' và lọc suy luận CoT."""
        from unittest.mock import MagicMock
        from core.translation.controllers.translation_controller import TranslationController
        from core.translation.llm.worker import TranslationWorker

        # LOGIC-05: Translation: không làm mất bản dịch
        mock_model = MagicMock()
        mock_model.get_all_data.return_value = [{"original": "Hello", "translation": "", "status": "PENDING"}]
        tc = TranslationController(mock_model)
        mock_worker = MagicMock()
        tc.worker = mock_worker
        tc._active_translation_index = 0
        tc._current_index = 0
        tc.on_finished(0, "Translation: Xin chào các bạn")
        self.assertEqual(tc.currentTranslation, "Xin chào các bạn")

        tc._active_translation_index = 0
        tc._current_index = 0
        tc.on_finished(0, "**Translation:** Xin chào bạn hiền")
        self.assertEqual(tc.currentTranslation, "Xin chào bạn hiền")

        # LOGIC-09: TranslationWorker._visible_translation lọc </think> khi không có <think>
        res = TranslationWorker._visible_translation("Thought process here...\n</think>Xin chào thế giới")
        self.assertEqual(res, "Xin chào thế giới")

        res_in_progress = TranslationWorker._visible_translation("<think>Thinking...")
        self.assertEqual(res_in_progress, "")

    def test_prompt_format_deepseek_and_reasoning_shield(self):
        """Kiểm tra định dạng DeepSeek và lá chắn chặn độc thoại suy luận rò rỉ."""
        from core.translation.llm.worker import TranslationWorker
        deepseek_prompt = PromptBuilder.build(
            story_summary="Summary",
            current_sub="身も心もすべてを捧げるためです",
            model_family="deepseek",
        )
        self.assertIn("<｜User｜>", deepseek_prompt)
        self.assertIn("<｜Assistant｜><think>", deepseek_prompt)

        # Chặn lặp lại prompt header
        echo_text = """--- CURRENT SUBTITLE TO TRANSLATE ---
身も心もすべてを捧げるためです
--- Output ---
Để dâng hết cả tâm hồn"""
        self.assertEqual(TranslationWorker._visible_translation(echo_text), "Để dâng hết cả tâm hồn")

        # Chặn độc thoại suy luận thô không có thẻ think
        raw_reasoning = """Wait, that can't be right. Let's think carefully.
First subtitle: it's about being everything...
Maybe better translation..."""
        self.assertEqual(TranslationWorker._visible_translation(raw_reasoning), "")

        # Trích xuất khi có So final output:
        full_monologue = raw_reasoning + """\nSo final output:\nĐể dâng trọn tâm hồn\n[TỪ GỐC]\n- 身 -> thân"""
        self.assertEqual(TranslationWorker._visible_translation(full_monologue), "Để dâng trọn tâm hồn")

if __name__ == "__main__":
    unittest.main()

