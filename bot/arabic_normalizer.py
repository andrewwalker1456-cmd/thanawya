"""
Thanaweya Amma Bot — Arabic Text Normalizer
Handles all Arabic text normalization for consistent search.
"""

import re
import unicodedata


# Arabic normalization mappings
ALEF_VARIANTS = "أإآٱ"
ALEF_BASE = "ا"
TEH_MARBUTA = "ة"
HA = "ه"
YA_BASE = "ي"
ALEF_MAQSURA = "ى"

# Arabic diacritics (tashkeel) Unicode range
DIACRITICS_PATTERN = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E4\u06E7\u06E8\u06EA-\u06ED]")

# Tatweel (kashida)
TATWEEL = "\u0640"

# Multiple spaces
MULTIPLE_SPACES = re.compile(r"\s+")

# Common Arabic prefixes that get fused with the next word
# e.g. "عبدالرحمن" should also match "عبد الرحمن"
ARABIC_PREFIXES = {"عبد", "ابو", "ابي", "أبو", "أبي"}

# Pattern to split fused Arabic compound names
# Splits after common prefixes: "عبدالرحمن" → ["عبد", "الرحمن"]
FUSED_PREFIX_PATTERN = re.compile(r"^(عبدال|ابوال|ابيل|أبوال|أبيل)")


class ArabicNormalizer:
    """Normalizes Arabic text for consistent search matching.

    Enhancements for name search:
    - Always normalizes ة ↔ ه at END of words (for names ending in ة/ه)
    - Always normalizes ى → ي (alef maqsura)
    - Generates extra tokens for fused compound names (عبدالرحمن → عبد + الرحمن)
    - Removes "ال" prefix from tokens for better matching
    """

    def __init__(self, normalize_teh: bool = False):
        self.normalize_teh = normalize_teh

    def normalize(self, text: str) -> str:
        """
        Fully normalize Arabic text for search purposes.

        Steps:
        1. Unicode NFC normalization
        2. Remove diacritics (tashkeel)
        3. Remove tatweel (kashida)
        4. Normalize alef variants (أ إ آ ٱ → ا)
        5. Normalize alef maqsura (ى → ي)
        6. Normalize teh marbuta at END of words (ة → ه) for search matching
        7. Optionally normalize ALL teh marbuta (ة → ه)
        8. Collapse multiple spaces
        9. Trim whitespace
        """
        if not text:
            return ""

        # Step 1: Unicode NFC normalization
        text = unicodedata.normalize("NFC", text)

        # Step 2: Remove diacritics
        text = DIACRITICS_PATTERN.sub("", text)

        # Step 3: Remove tatweel (kashida)
        text = text.replace(TATWEEL, "")

        # Step 4: Normalize alef variants
        for variant in ALEF_VARIANTS:
            text = text.replace(variant, ALEF_BASE)

        # Step 5: Normalize alef maqsura
        text = text.replace(ALEF_MAQSURA, YA_BASE)

        # Step 6: Normalize teh marbuta at END of words (for name matching)
        # "فاطمة" → "فاطمه" only when ة is the last character of a word
        if not self.normalize_teh:
            text = re.sub(r"(\w)ة(\s|$)", r"\1ه\2", text)
            # Also handle final ة at end of string
            text = re.sub(r"(\w)ة$", r"\1ه", text)
        else:
            text = text.replace(TEH_MARBUTA, HA)

        # Step 7: Collapse multiple spaces
        text = MULTIPLE_SPACES.sub(" ", text)

        # Step 8: Trim
        text = text.strip()

        return text

    def normalize_for_storage(self, text: str) -> str:
        """Normalize text for storage/indexing (always full normalization)."""
        return self.normalize(text)

    def normalize_for_search(self, text: str) -> str:
        """Normalize user search input."""
        return self.normalize(text)

    def get_search_tokens(self, text: str) -> "List[str]":
        """
        Extract tokens from text for index lookup.
        Returns the original normalized tokens PLUS extra tokens for:
        - Fused compound names (عبدالرحمن → ["عبدالرحمن", "عبد", "الرحمن", "رحمن"])
        - Words with "ال" prefix also stored without it (الرحمن → رحمن)

        This ensures "عبدالرحمن" and "عبد الرحمن" find the same records.
        """
        norm = self.normalize(text)
        if not norm:
            return []

        base_tokens = norm.split()
        extra_tokens = []

        for token in base_tokens:
            extra_tokens.append(token)

            # Handle fused compound: "عبدالرحمن" → add "عبد" and "الرحمن" and "رحمن"
            m = FUSED_PREFIX_PATTERN.match(token)
            if m:
                prefix_part = "عبد"
                rest_part = token[m.end():]  # "الرحمن"
                extra_tokens.append(prefix_part)
                extra_tokens.append(rest_part)
                # Also add without "ال"
                if rest_part.startswith("ال"):
                    extra_tokens.append(rest_part[2:])  # "رحمن"

            # For non-fused tokens: also store without "ال" prefix
            elif token.startswith("ال") and len(token) > 3:
                extra_tokens.append(token[2:])  # Remove "ال"

        # Deduplicate while preserving order
        seen = set()
        result = []
        for t in extra_tokens:
            if t not in seen and len(t) >= 2:
                seen.add(t)
                result.append(t)

        return result

    def matches(self, stored_text: str, search_text: str) -> bool:
        """
        Check if stored text matches search text after normalization.
        Handles the teh/ha equivalence even when normalize_teh is False.
        """
        norm_stored = self.normalize(stored_text)
        norm_search = self.normalize(search_text)

        if norm_stored == norm_search:
            return True

        # If normalize_teh is False, also check with full teh/ha equivalence
        if not self.normalize_teh:
            norm_stored_th = norm_stored.replace(TEH_MARBUTA, HA)
            norm_search_th = norm_search.replace(TEH_MARBUTA, HA)
            if norm_stored_th == norm_search_th:
                return True

        return False
