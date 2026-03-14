from src.translation.client import TranslationClient, TranslationError

SUPPORTED_LANGUAGES: dict[str, str] = {
    "lug": "Luganda",
    "ach": "Acholi",
    "nyn": "Runyankole",
    "teo": "Ateso",
    "lgg": "Lugbara",
    "eng": "English",
}

__all__ = ["TranslationClient", "TranslationError", "SUPPORTED_LANGUAGES"]
