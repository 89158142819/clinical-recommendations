import unittest

from text_cleaner import clean_extracted_pages, clean_full_text, _get_morph_analyzer, _is_dictionary_word, _split_concatenated_token


class TextCleanerTests(unittest.TestCase):

    def test_removes_page_labels_and_page_numbers(self):
        source = (
            "[Страница 1]\n"
            "Заголовок документа\n"
            "Основной текст рекомендации.\n"
            "1\n"
            "[Страница 2]\n"
            "Продолжение основного текста.\n"
            "2\n"
        )
        cleaned = clean_full_text(source)
        self.assertNotIn("[Страница", cleaned)
        self.assertNotRegex(cleaned, r"(?m)^\s*[12]\s*$")
        self.assertIn("Основной текст рекомендации.", cleaned)
        self.assertIn("Продолжение основного текста.", cleaned)

    def test_removes_repeated_headers_and_footers(self):
        pages = [
            {"text": "Клинические рекомендации\nТекст первой страницы.\nПодвал документа"},
            {"text": "Клинические рекомендации\nТекст второй страницы.\nПодвал документа"},
            {"text": "Клинические рекомендации\nТекст третьей страницы.\nПодвал документа"},
        ]
        cleaned, removed = clean_extracted_pages(pages)
        self.assertNotIn("Клинические рекомендации", cleaned)
        self.assertNotIn("Подвал документа", cleaned)
        self.assertIn("Текст первой страницы.", cleaned)
        self.assertTrue(removed)

    def test_preserves_medical_numbered_list(self):
        source = (
            "[Страница 1]\n"
            "Раздел диагностики\n"
            "1. Общий анализ крови.\n"
            "2. Биохимический анализ крови.\n"
            "3. Исследование уровня глюкозы.\n"
        )
        cleaned = clean_full_text(source)
        self.assertIn("1. Общий анализ крови.", cleaned)
        self.assertIn("2. Биохимический анализ крови.", cleaned)
        self.assertIn("3. Исследование уровня глюкозы.", cleaned)

    def test_joins_hyphenated_word(self):
        cleaned = clean_full_text("Лабора-\nторное исследование.")
        self.assertIn("Лабораторное исследование.", cleaned)

    def test_repairs_concatenated_words_from_pdf(self):
        source = (
            "рентгенографиипораженной части костногоскелета. "
            "анамнез, жалобыили физикальные данныепозволяют "
            "предположитьСВТ."
        )
        analyzer = _get_morph_analyzer()
        print("DEBUG_ANALYZER", analyzer is not None, hasattr(analyzer, "word_is_known") if analyzer else None)
        if analyzer:
            for word in ["рентгенографии", "пораженной", "костного", "скелета", "жалобы", "или", "данные", "позволяют"]:
                parsed = analyzer.parse(word)
                print("DEBUG_WORD", word, analyzer.word_is_known(word) if hasattr(analyzer, "word_is_known") else None,
                      [(p.score, [type(m[0]).__name__ for m in p.methods_stack]) for p in parsed[:2]])
        print("DEBUG_SPLIT", _split_concatenated_token("рентгенографиипораженной"))
        cleaned = clean_full_text(source)
        self.assertIn("рентгенографии пораженной", cleaned)
        self.assertIn("костного скелета", cleaned)
        self.assertIn("жалобы или", cleaned)
        self.assertIn("данные позволяют", cleaned)
        self.assertIn("предположить СВТ", cleaned)

    def test_preserves_valid_medical_words(self):
        source = "электрокардиограмма новорождённого рентгеноденситометрия."
        cleaned = clean_full_text(source)
        self.assertIn("электрокардиограмма", cleaned)
        self.assertIn("новорождённого", cleaned)
        self.assertIn("рентгеноденситометрия", cleaned)

    def test_preserves_doses_and_ranges(self):
        cleaned = clean_full_text("Назначить 500 мг 2 раза в сутки. Уровень 3,5–5,5 ммоль/л.")
        self.assertIn("500 мг", cleaned)
        self.assertIn("3,5–5,5 ммоль/л", cleaned)


if __name__ == "__main__":
    unittest.main()
