"""Tests for consent name/number extraction (voclyp/live/entities.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voclyp.live.entities import (  # noqa: E402
    extract_entities,
    extract_name,
    extract_phone,
    transliterate_devanagari,
)


class NameExtraction(unittest.TestCase):
    def test_full_romanized_name_no_filler(self):
        name, conf = extract_name("customer ka naam Kartik Chavan hai")
        self.assertEqual(name, "Kartik Chavan")
        self.assertGreater(conf, 0.5)

    def test_single_romanized_name_drops_hai(self):
        # The reported bug: "kartik hai" should yield "Kartik", never "Kartik Hai".
        name, _ = extract_name("mera naam kartik hai")
        self.assertEqual(name, "Kartik")

    def test_devanagari_name_transliterated_to_english(self):
        name, _ = extract_name("मेरा नाम कार्तिक चव्हाण है")
        self.assertNotRegex(name or "", r"[\u0900-\u097F]")  # no Devanagari left
        self.assertTrue((name or "").lower().startswith("kaartik")
                        or (name or "").lower().startswith("kartik"))
        self.assertEqual(len(name.split()), 2)  # full name, both tokens kept

    def test_english_my_name_is(self):
        name, _ = extract_name("Hello, my name is Rahul Sharma and I work here")
        self.assertEqual(name, "Rahul Sharma")

    def test_no_cue_returns_none(self):
        # A normal lowercase sentence is never mistaken for a name.
        name, conf = extract_name("orthopaedic mattress chahiye pith dard hai")
        self.assertIsNone(name)
        self.assertEqual(conf, 0.0)

    def test_cueless_capitalised_name(self):
        # Rep just says the name, no "naam"/"my name is" cue.
        name, conf = extract_name("Kartik Chavan")
        self.assertEqual(name, "Kartik Chavan")
        self.assertGreater(conf, 0.0)

    def test_cueless_single_name(self):
        name, _ = extract_name("Rahul")
        self.assertEqual(name, "Rahul")

    def test_cueless_with_greeting_filler(self):
        name, _ = extract_name("haan Rahul Sharma")
        self.assertEqual(name, "Rahul Sharma")

    def test_cueless_devanagari_short_utterance(self):
        name, _ = extract_name("कार्तिक चव्हाण")
        self.assertIsNotNone(name)
        self.assertNotRegex(name or "", r"[\u0900-\u097F]")

    def test_cueless_name_before_number(self):
        out = extract_entities("Rahul Sharma 9876543210")
        self.assertEqual(out["name"], "Rahul Sharma")
        self.assertEqual(out["phone"], "+919876543210")

    def test_restating_name_corrects_earlier(self):
        # Rep first says just "kartik hai", then corrects with the full name.
        rolling = "mera naam kartik hai mera naam kartik chavan hai"
        name, _ = extract_name(rolling)
        self.assertEqual(name, "Kartik Chavan")


class PhoneExtraction(unittest.TestCase):
    def test_plain_10_digit(self):
        phone, _ = extract_phone("WhatsApp number 9876543210")
        self.assertEqual(phone, "+919876543210")

    def test_country_code(self):
        phone, _ = extract_phone("number +91 98765 43210")
        self.assertEqual(phone, "+919876543210")

    def test_spoken_hindi_digits(self):
        phone, _ = extract_phone(
            "WhatsApp number nau aath saat chhe paanch char teen do ek shunya"
        )
        self.assertEqual(phone, "+919876543210")

    def test_devanagari_spoken_digits(self):
        phone, _ = extract_phone("नंबर नौ आठ सात छह पांच चार तीन दो एक शून्य")
        self.assertEqual(phone, "+919876543210")

    def test_devanagari_numerals(self):
        phone, _ = extract_phone("नंबर ९८७६५४३२१०")
        self.assertEqual(phone, "+919876543210")

    def test_restating_number_corrects_earlier(self):
        rolling = "number 9876543210 nahi, number 9000000001"
        phone, _ = extract_phone(rolling)
        self.assertEqual(phone, "+919000000001")

    def test_spoken_number_correction(self):
        rolling = ("number nau aath saat chhe paanch char teen do ek shunya "
                   "galat, number nau zero zero zero zero zero zero zero zero ek")
        phone, _ = extract_phone(rolling)
        self.assertEqual(phone, "+919000000001")

    def test_non_mobile_digits_rejected(self):
        # Does not start 6-9 -> not an Indian mobile -> don't surface junk.
        self.assertEqual(extract_phone("mera number 1234567890")[0], None)

    def test_half_number_not_emitted(self):
        self.assertEqual(extract_phone("number nau aath saat")[0], None)

    def test_split_number_groups(self):
        phone, _ = extract_phone("WhatsApp number 98765 43210")
        self.assertEqual(phone, "+919876543210")


class NameCleanup(unittest.TestCase):
    def test_full_name_with_cue_and_copula(self):
        name, _ = extract_name("mera naam kartik chavan hai")
        self.assertEqual(name, "Kartik Chavan")

    def test_messy_asr_latin_is_canonicalised(self):
        # Sarvam returns doubled vowels + trailing copula/punctuation.
        name, _ = extract_name("Mera naam Kaartik Chauhaan hai!")
        self.assertEqual(name, "Kartik Chavan")

    def test_devanagari_full_name(self):
        name, _ = extract_name("मेरा नाम कार्तिक चव्हाण है")
        self.assertEqual(name, "Kartik Chavan")

    def test_direct_name_no_cue_titlecase(self):
        name, _ = extract_name("Kartik Chavan")
        self.assertEqual(name, "Kartik Chavan")

    def test_direct_name_no_cue_lowercase(self):
        name, _ = extract_name("kartik chavan")
        self.assertEqual(name, "Kartik Chavan")

    def test_need_is_not_treated_as_name(self):
        self.assertEqual(extract_name("back pain hai")[0], None)
        self.assertEqual(extract_name("cooling chahiye")[0], None)

    def test_restated_name_corrects_earlier(self):
        name, _ = extract_name("mera naam kartik hai mera naam kartik chavan hai")
        self.assertEqual(name, "Kartik Chavan")

    def test_self_correction_without_recue(self):
        # "Rahul... no, Kartik" — corrected without saying "mera naam" again.
        name, _ = extract_name("mera naam rahul hai, rahul nahi kartik")
        self.assertEqual(name, "Kartik")

    def test_self_correction_full_name(self):
        name, _ = extract_name("Rahul nahi Kartik Chavan")
        self.assertEqual(name, "Kartik Chavan")

    def test_spoken_digit_not_glued_to_name(self):
        # "...Kartik nau aath" must not become "Kartik Nau".
        name, _ = extract_name("mera naam Kartik nau aath saat")
        self.assertEqual(name, "Kartik")


class Combined(unittest.TestCase):
    def test_name_and_phone_together(self):
        out = extract_entities(
            "customer ka naam Kartik Chavan hai, WhatsApp number 9876543210"
        )
        self.assertEqual(out["name"], "Kartik Chavan")
        self.assertEqual(out["phone"], "+919876543210")

    def test_transliterate_basic(self):
        self.assertNotRegex(transliterate_devanagari("राहुल"), r"[\u0900-\u097F]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
