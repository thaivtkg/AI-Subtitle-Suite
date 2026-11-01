import unittest
from core.utils.translation_detector import (
    is_vietnamese_translated,
    find_first_untranslated_index,
    count_translated_segments,
)


class TestTranslationDetector(unittest.TestCase):
    def test_tc_trans_01_empty_and_placeholder(self):
        self.assertFalse(is_vietnamese_translated(""))
        self.assertFalse(is_vietnamese_translated("   "))
        self.assertFalse(is_vietnamese_translated(None))
        self.assertFalse(is_vietnamese_translated("[ Chưa có nội dung ]"))
        self.assertFalse(is_vietnamese_translated({"text": "[ Chưa có nội dung ]"}))

    def test_tc_trans_02_cjk_japanese_and_korean(self):
        # Kanji, Hiragana, Katakana
        self.assertFalse(is_vietnamese_translated("どんな暗闇でも"))
        self.assertFalse(is_vietnamese_translated("アイ・ラブ・ユー"))
        self.assertFalse(is_vietnamese_translated({"text": "こんにちは世界"}))
        # Korean Hangul
        self.assertFalse(is_vietnamese_translated("안녕하세요"))

    def test_tc_trans_03_cyrillic_russian(self):
        self.assertFalse(is_vietnamese_translated("Привет, как дела?"))
        self.assertFalse(is_vietnamese_translated("До свидания."))

    def test_tc_trans_04_english(self):
        self.assertFalse(is_vietnamese_translated("What are you doing?"))
        self.assertFalse(is_vietnamese_translated("Lord, help my world."))
        self.assertFalse(is_vietnamese_translated("In the beginning there was light."))
        self.assertFalse(is_vietnamese_translated({"text": "You know that is not true"}))

    def test_tc_trans_05_vietnamese_with_diacritics(self):
        self.assertTrue(is_vietnamese_translated("Cuối cùng đã tìm thấy ngài rồi Ma Vương"))
        self.assertTrue(is_vietnamese_translated("Xin chào các bạn."))
        self.assertTrue(is_vietnamese_translated("Dù cho bóng tối có bao trùm"))
        self.assertTrue(is_vietnamese_translated({"text": "Tôi là người dịch"}))

    def test_tc_trans_06_conversational_particles(self):
        self.assertTrue(is_vietnamese_translated("OK"))
        self.assertTrue(is_vietnamese_translated("Alo"))
        self.assertTrue(is_vietnamese_translated("Bye"))
        self.assertTrue(is_vietnamese_translated("Wow!"))

    def test_tc_trans_07_matching_original_text(self):
        # If text equals original_text from speech recognition, it's not translated
        self.assertFalse(is_vietnamese_translated({
            "text": "Hello world",
            "original_text": "Hello world"
        }))

    def test_tc_trans_08_helpers_count_and_find_untranslated(self):
        segs = [
            {"stt": "1", "text": "Câu một đã dịch"},
            {"stt": "2", "text": "Câu hai đã dịch"},
            {"stt": "3", "text": "Câu ba đã dịch"},
            {"stt": "4", "text": "どんな暗闇でも"},
            {"stt": "5", "text": "[ Chưa có nội dung ]"},
        ]
        translated, total = count_translated_segments(segs)
        self.assertEqual(translated, 3)
        self.assertEqual(total, 5)
        self.assertEqual(find_first_untranslated_index(segs), 4)

        # All translated
        all_translated = [
            {"stt": "1", "text": "Đã dịch 1"},
            {"stt": "2", "text": "Đã dịch 2"},
        ]
        t2, tot2 = count_translated_segments(all_translated)
        self.assertEqual(t2, 2)
        self.assertEqual(tot2, 2)
        self.assertIsNone(find_first_untranslated_index(all_translated))


if __name__ == "__main__":
    unittest.main()
