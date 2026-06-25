"""Extract customer name and phone from rolling consent transcript text.

The rep typically speaks a short Hindi / Hindi-English line such as
"customer ka naam Kartik Chavan hai, WhatsApp number nau aath saat ...".
Sarvam returns this in Devanagari when the rep speaks Hindi, so this module:

1. Locates a name cue ("naam"/"नाम"/"my name is" ...).
2. Captures the *whole* name (multiple words), not just the first token.
3. Strips filler/stopwords ("hai", "है", "ji", "customer", ...) from both ends.
4. Transliterates any Devanagari name into readable Latin/English so the field
   shows "Kartik Chavan" rather than "कार्तिक चव्हाण".

Phone parsing accepts real numerals, Devanagari numerals, and digit *words*
spoken in Hindi or English, and always normalises to the last 10 digits.
"""
from __future__ import annotations

import re

# --- Devanagari -> Latin transliteration (names; offline, deterministic) -----
# Pragmatic ITRANS-style mapping with word-final schwa deletion. Not a perfect
# linguistic transliteration, but produces readable English names; the rep can
# always correct the editable text field.
_DEV_INDEP_VOWELS = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
    "ऋ": "ri", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऒ": "o",
}
_DEV_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॊ": "o",
}
_DEV_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh",
    "स": "s", "ह": "h", "ळ": "l",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh",
    "फ़": "f", "य़": "y",
}
_NUKTA = "\u093c"
_VIRAMA = "\u094d"
_ANUSVARA = "\u0902"
_CHANDRABINDU = "\u0901"
_VISARGA = "\u0903"

_DEV_DIGITS = {
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def _has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI_RE.search(text))


def transliterate_devanagari(word: str) -> str:
    """Transliterate a single Devanagari word into Latin script."""
    if not _has_devanagari(word):
        return word
    out: list[str] = []
    chars = word
    n = len(chars)
    i = 0
    while i < n:
        ch = chars[i]
        if ch in _DEV_DIGITS:
            out.append(_DEV_DIGITS[ch])
            i += 1
            continue
        if ch in _DEV_CONSONANTS:
            cons = _DEV_CONSONANTS[ch]
            j = i + 1
            if j < n and chars[j] == _NUKTA:
                j += 1  # nukta already folded into the base mapping
            following = chars[j] if j < n else ""
            if following == _VIRAMA:
                out.append(cons)
                i = j + 1
            elif following in _DEV_MATRAS:
                out.append(cons + _DEV_MATRAS[following])
                i = j + 1
            else:
                out.append(cons + "a")  # inherent schwa
                i = j
            continue
        if ch in _DEV_INDEP_VOWELS:
            out.append(_DEV_INDEP_VOWELS[ch])
        elif ch in _DEV_MATRAS:
            out.append(_DEV_MATRAS[ch])
        elif ch in (_ANUSVARA, _CHANDRABINDU):
            out.append("n")
        elif ch == _VISARGA:
            out.append("h")
        elif ch in (_VIRAMA, _NUKTA):
            pass
        else:
            out.append(ch)
        i += 1
    result = "".join(out)
    # Word-final schwa deletion: कार्तिक -> "kaartika" -> "kaartik".
    if len(result) > 2 and result.endswith("a") and not result.endswith("aa"):
        result = result[:-1]
    return result


# --- name extraction ---------------------------------------------------------
# Words that are never part of the name; used to trim both ends of the capture
# and to detect where the name stops (e.g. the trailing Hindi copula "hai").
_NAME_STOP = {
    "hai", "hain", "है", "हैं", "tha", "thi",
    "ji", "जी", "sir", "madam", "maam", "ma'am",
    "and", "और", "aur",
    "naam", "नाम", "nam", "naame",
    "mera", "मेरा", "mere", "meri", "mai", "main", "मैं", "hum",
    "customer", "ग्राहक", "grahak", "client",
    "ka", "का", "ki", "की", "ke", "के", "se", "से", "ko", "को",
    "number", "नंबर", "नम्बर", "no", "whatsapp", "whats", "app",
    "phone", "मोबाइल", "mobile", "फोन", "फ़ोन", "contact",
    "yeh", "ये", "this", "is", "are", "the", "a", "an",
}

_NAME_CUE = re.compile(
    r"(?:"
    r"मेरा\s*नाम|नाम\s*है|नाम|"
    r"my\s*name\s*is|name\s*is|"
    r"mera\s*naam|naam\s*hai|naam|"
    r"this\s*is|i\s*am|i'?m"
    r")",
    re.IGNORECASE,
)

# Correction / disfluency markers. When the speaker self-corrects ("Rahul nahi
# Kartik", "galat, ...", "sorry ..."), everything BEFORE the marker is a false
# start and must be discarded — the authoritative value is what follows. We
# deliberately exclude bare "no" because Hindi speakers say "no"/"number" for
# the phone ("mera no hai ..."). This is disfluency-repair by segmentation.
_CORRECTION_CUE = re.compile(
    r"(?:"
    r"नहीं|नहीँ|नही|"
    r"\bnahi+\b|\bnahin\b|\bnai\b|"
    r"\bgalat\b|गलत|"
    r"\bsorry\b|\bactually\b|\boops\b|"
    r"\bmatlab\b|मतलब|"
    r"\bwrong\b|\bcorrection\b|"
    r"\bdobara\b|दोबारा|\bfir\s*se\b|फिर\s*से|\bagain\b"
    r")",
    re.IGNORECASE,
)

_NAME_TOKEN = re.compile(r"[\u0900-\u097FA-Za-z]+")

# Greetings / acknowledgements that are never a name but are common in consent
# audio ("haan Rahul", "ok Kartik chavan"). Used only by the cue-less path.
_GREETING_FILLER = {
    "hello", "hi", "hey", "namaste", "namaskar", "ok", "okay", "yes", "no",
    "yeah", "haan", "han", "ha", "haa", "theek", "thik", "accha", "acha",
    "arre", "arrey", "matlab", "bhai", "please", "thanks", "thank", "welcome",
    "bolo", "bol", "batao", "bata", "likho", "likh", "haanji", "hanji",
    "hua", "huaa", "hoon", "hun", "hu", "ho", "raha", "rahi", "rahe",
}

# Common non-name words that can show up as a short utterance on the name field
# ("back pain", "cooling chahiye"). Guards the cue-less lowercase path so we
# never turn a need into a name.
_NOT_A_NAME = {
    "back", "pain", "spine", "support", "neck", "shoulder", "cooling", "cool",
    "hot", "warm", "garmi", "thanda", "mattress", "gadda", "gaddi", "bed",
    "budget", "price", "cost", "paisa", "paise", "emi", "loan", "trial",
    "firm", "soft", "medium", "hard", "sleep", "neend", "dard", "problem",
    "chahiye", "chahie", "chaiye", "dikhao", "dikha", "dekho", "dekh",
    "order", "delivery", "warranty", "size", "queen", "king", "single",
    "double", "product", "model", "ortho", "luxe", "snowtec",
}

# Editable alias list: clean spellings for common Indian names that ASR / our
# transliteration tends to mangle (kaartik -> kartik, चव्हाण -> chavhan ->
# Chavan). Keys are the *tidied* lowercase form (doubled vowels already
# collapsed). Add more as you onboard stores — the field is always editable.
_NAME_CANON = {
    "kartik": "Kartik", "karthik": "Kartik", "kartick": "Kartik",
    "kartic": "Kartik", "kaartik": "Kartik",
    "chavan": "Chavan", "chavhan": "Chavan", "chauhan": "Chavan",
    "chauhan": "Chavan", "chaavan": "Chavan",
    "rahul": "Rahul", "rohan": "Rohan", "rohit": "Rohit", "amit": "Amit",
    "sneha": "Sneha", "priya": "Priya", "pooja": "Pooja", "neha": "Neha",
    "raj": "Raj", "ravi": "Ravi", "vijay": "Vijay", "anjali": "Anjali",
}

_VOWEL_RUN = re.compile(r"([aeiou])\1+", re.IGNORECASE)


def _tidy_latin(word: str) -> str:
    """Make a transliterated/ASR token read like a clean name: drop stray
    punctuation/digits and collapse doubled vowels (kaartik -> kartik)."""
    w = re.sub(r"[^A-Za-z'.\-]", "", word)
    w = _VOWEL_RUN.sub(r"\1", w)
    return w


def _to_name_word(tok: str) -> str | None:
    """Devanagari/ASR token -> a single clean, title-cased English name word."""
    latin = transliterate_devanagari(tok) if _has_devanagari(tok) else tok
    latin = _tidy_latin(latin)
    if not latin:
        return None
    canon = _NAME_CANON.get(latin.lower())
    if canon:
        return canon
    return latin[:1].upper() + latin[1:].lower()


def _format_name(tokens: list[str]) -> str | None:
    """Transliterate + tidy + title-case a run of name tokens into English."""
    words = [w for w in (_to_name_word(t) for t in tokens) if w]
    name = " ".join(words).strip()
    return name or None


def _clean_name(after_cue: str) -> str | None:
    """Pick the name tokens that follow a cue, trimmed of filler, in English."""
    picked: list[str] = []
    for tok in _NAME_TOKEN.findall(after_cue):
        low = tok.lower()
        if low in _NAME_STOP or tok in _NAME_STOP or low in _GREETING_FILLER:
            if picked:
                break          # name finished (e.g. hit trailing "hai")
            continue           # skip leading filler ("mera naam ...")
        # The number has started ("...Kartik nau aath saat") — name is done.
        if any(ch.isdigit() for ch in tok) or low in _SPOKEN_DIGIT or tok in _SPOKEN_DIGIT:
            break
        picked.append(tok)
        if len(picked) >= 4:   # full names rarely exceed four tokens
            break
    return _format_name(picked) if picked else None


_CAP_LATIN = re.compile(r"^[A-Z][a-zA-Z'.\-]+$")


def _is_cueless_skip(tok: str) -> bool:
    low = tok.lower()
    return (low in _NAME_STOP or tok in _NAME_STOP
            or low in _GREETING_FILLER or low in _SPOKEN_DIGIT
            or tok in _SPOKEN_DIGIT)


def _extract_name_cueless(text: str) -> str | None:
    """Capture a name when the speaker did NOT say a cue ("naam"/"my name is").

    Two safe signals (so we never turn a normal sentence into a name):
      * Capitalised run — ASR capitalises proper nouns, so a run of Capitalised
        Latin tokens ("Kartik Chavan") is a strong name signal while a lowercase
        sentence ("orthopaedic mattress chahiye") is not. Last run wins.
      * Short name-only utterance — when the speaker just says the name
        ("कार्तिक चव्हाण", "Rahul"), the whole (pre-number) utterance is 1-2
        non-filler tokens; treat that as the name.
    """
    region = text
    ctx = _PHONE_CONTEXT.search(text)
    if ctx:
        region = text[:ctx.start()]  # the name is stated before the number
    tokens = _NAME_TOKEN.findall(region)
    if not tokens:
        return None

    # Capitalised run (Latin proper nouns).
    runs: list[list[str]] = []
    cur: list[str] = []
    for tok in tokens:
        if not _has_devanagari(tok) and _CAP_LATIN.match(tok) and not _is_cueless_skip(tok):
            cur.append(tok)
        else:
            if cur:
                runs.append(cur)
                cur = []
    if cur:
        runs.append(cur)
    if runs:
        return _format_name(runs[-1][:3])

    # Short, name-only utterance: the speaker just says the name with no cue
    # ("कार्तिक चव्हाण", "Kartik Chavan", or even a lowercase ASR "kartik chavan").
    non_filler = [t for t in tokens
                  if not _is_cueless_skip(t) and not any(c.isdigit() for c in t)]
    if 1 <= len(non_filler) <= 3 and len(tokens) <= 4:
        # Devanagari or Capitalised -> unambiguously a name.
        if any(_has_devanagari(t) or t[:1].isupper() for t in non_filler):
            return _format_name(non_filler[:3])
        # All-lowercase Latin (Sarvam sometimes lowercases): accept on the
        # name-focused field unless any token is a common non-name word.
        if not any(t.lower() in _NOT_A_NAME for t in non_filler):
            return _format_name(non_filler[:3])
    return None


def extract_name(text: str) -> tuple[str | None, float]:
    """Return (english_name, confidence) from a consent transcript.

    Correction-aware by segmentation: we find the LAST point where the speaker
    (re)started stating the name — either a name cue ("mera naam", "my name
    is") or a self-correction ("Rahul nahi Kartik", "galat ...") — and read the
    name only from there. A false first try ("Rahul") is discarded the moment
    the speaker corrects, instead of sticking forever. With no cue at all we
    fall back to a conservative cue-less capture (plain "Kartik Chavan").
    """
    if not text:
        return None, 0.0

    last_pos, last_kind = -1, ""
    for m in _NAME_CUE.finditer(text):
        if m.end() > last_pos:
            last_pos, last_kind = m.end(), "cue"
    for m in _CORRECTION_CUE.finditer(text):
        if m.end() > last_pos:
            last_pos, last_kind = m.end(), "correction"

    if last_pos >= 0:
        tail = text[last_pos:]
        if last_kind == "cue":
            cand = _clean_name(tail)
            if cand and len(cand) >= 2:
                return cand, 0.85
        # Correction (or a cue whose tail wasn't clean): the corrected name is
        # usually said plainly, so try the cue-less reader on the tail.
        cand = _extract_name_cueless(tail) or _clean_name(tail)
        if cand and len(cand) >= 2:
            conf = 0.75 if last_kind == "correction" else 0.7
            return cand, conf

    cueless = _extract_name_cueless(text)
    if cueless and len(cueless) >= 2:
        return cueless, 0.6
    return None, 0.0


# --- phone extraction --------------------------------------------------------
_SPOKEN_DIGIT = {
    "0": "0", "zero": "0", "shunya": "0", "sunya": "0",
    "शून्य": "0", "ज़ीरो": "0", "जीरो": "0", "०": "0",
    "1": "1", "one": "1", "ek": "1", "एक": "1", "१": "1",
    "2": "2", "two": "2", "do": "2", "दो": "2", "२": "2",
    "3": "3", "three": "3", "teen": "3", "tin": "3", "तीन": "3", "तिन": "3", "३": "3",
    "4": "4", "four": "4", "char": "4", "chaar": "4", "चार": "4", "४": "4",
    "5": "5", "five": "5", "paanch": "5", "panch": "5", "पांच": "5", "पाँच": "5", "५": "5",
    "6": "6", "six": "6", "chhe": "6", "chhah": "6", "che": "6",
    "छह": "6", "छः": "6", "छ": "6", "६": "6",
    "7": "7", "seven": "7", "saat": "7", "सात": "7", "७": "7",
    "8": "8", "eight": "8", "aath": "8", "आठ": "8", "८": "8",
    "9": "9", "nine": "9", "nau": "9", "नौ": "9", "९": "9",
}

_PHONE_CONTEXT = re.compile(
    r"(?:whatsapp|whats\s*app|number|phone|mobile|contact|नंबर|नम्बर|मोबाइल|"
    r"फोन|फ़ोन|व्हाट्सऐप|व्हाट्सएप|वॉट्सऐप)",
    re.IGNORECASE,
)
_ASCII_DIGIT_MAP = {ord(dev): ascii_ for dev, ascii_ in _DEV_DIGITS.items()}


def _fold_digits(text: str) -> str:
    """Replace Devanagari numerals (०-९) with ASCII so \\d handling is uniform."""
    return text.translate(_ASCII_DIGIT_MAP)


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", _fold_digits(raw))
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) > 10:
        return f"+91{digits[-10:]}"
    return raw.strip()


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[\u0900-\u097Fa-zA-Z0-9]+", text)


def spoken_digits_from_text(text: str) -> str:
    """Collapse spoken digit words (Hindi/English) into a digit string."""
    digits: list[str] = []
    for token in _tokenize_words(text):
        key = token.lower()
        if key in _SPOKEN_DIGIT:
            digits.append(_SPOKEN_DIGIT[key])
        elif token.isdigit():
            digits.extend(token)  # a run like "98765" contributes every digit
    return "".join(digits)


def extract_spoken_phone(text: str) -> str | None:
    """Find a 10-digit Indian mobile spoken as Hindi/English number words."""
    if not text:
        return None
    best = None
    for match in _PHONE_CONTEXT.finditer(text):
        window = text[match.end(): match.end() + 140]
        digits = spoken_digits_from_text(window)
        if len(digits) >= 10:
            best = normalize_phone(digits[-10:])  # last cue wins (correction)
    if best:
        return best
    digits = spoken_digits_from_text(text)
    if len(digits) >= 10:
        return normalize_phone(digits[-10:])
    return None


def _pick_indian_mobile(digits: str) -> str | None:
    """Choose a plausible 10-digit Indian mobile from a digit string.

    Returns the RIGHTMOST 10-digit window that starts with 6-9 (valid mobile),
    which strips a leading "0"/"91" country code and prefers the most recently
    spoken number. Returns None when no window looks like a mobile, so we never
    surface junk like "1234567890" or a half-spoken number.
    """
    if len(digits) < 10:
        return None
    for start in range(len(digits) - 10, -1, -1):
        window = digits[start:start + 10]
        if window[0] in "6789":
            return normalize_phone(window)
    return None


def extract_phone(text: str) -> tuple[str | None, float]:
    """Return (e164_phone, confidence) from a consent transcript.

    Correction-aware: digits are read only from AFTER the last correction
    ("nahi"/"galat") or fresh number cue ("number"/"WhatsApp"), so a restated
    number replaces the old one instead of blending old+new digits. Validated
    as an Indian mobile so noise is rejected rather than shown.
    """
    if not text:
        return None, 0.0
    text = _fold_digits(text)

    reset = 0
    for pat in (_CORRECTION_CUE, _PHONE_CONTEXT):
        for m in pat.finditer(text):
            if m.end() > reset:
                reset = m.end()

    # Prefer the segment after the last reset (the corrected / cued number),
    # then fall back to the whole transcript.
    for region, conf in ((text[reset:], 0.9), (text, 0.8)):
        phone = _pick_indian_mobile(spoken_digits_from_text(region))
        if phone:
            return phone, conf
    return None, 0.0


def extract_entities(text: str) -> dict:
    """Return {name, phone, name_confidence, phone_confidence} from transcript."""
    out = {"name": None, "phone": None, "name_confidence": 0.0, "phone_confidence": 0.0}
    if not text or not text.strip():
        return out
    name, name_conf = extract_name(text)
    phone, phone_conf = extract_phone(text)
    out["name"] = name
    out["name_confidence"] = name_conf
    out["phone"] = phone
    out["phone_confidence"] = phone_conf
    return out
