"""
Amazon marketplace country -> locale code mapping, used to pick the right
language suffix (e.g. " - en-US", " - de-DE") when writing attribute
headers into an Amplifi-style template. Amplifi's attribute columns are
always named "<attribute_path> - <locale>", and that locale has to match
whichever Amazon marketplace/country the data is for -- a masterfile
filled for Amazon.de should land in the template as "- de-DE" columns,
not "- en-US".

This list covers every marketplace Amazon currently operates in (North
America, Europe, the Middle East/Africa, and Asia-Pacific). If Amazon
opens a new marketplace, it only needs one new entry here -- nothing else
in the fill tool has to change.
"""

from __future__ import annotations

# (display label, country code, locale code) -- ordered roughly the way
# Seller Central groups marketplaces: North America, Europe, Middle
# East/Africa, then Asia-Pacific.
AMAZON_MARKETPLACES: list[tuple[str, str, str]] = [
    ("United States (US)", "US", "en-US"),
    ("Canada (CA)", "CA", "en-CA"),
    ("Mexico (MX)", "MX", "es-MX"),
    ("Brazil (BR)", "BR", "pt-BR"),
    ("United Kingdom (UK)", "UK", "en-GB"),
    ("Germany (DE)", "DE", "de-DE"),
    ("France (FR)", "FR", "fr-FR"),
    ("Italy (IT)", "IT", "it-IT"),
    ("Spain (ES)", "ES", "es-ES"),
    ("Netherlands (NL)", "NL", "nl-NL"),
    ("Sweden (SE)", "SE", "sv-SE"),
    ("Poland (PL)", "PL", "pl-PL"),
    ("Belgium (BE)", "BE", "nl-BE"),
    ("Ireland (IE)", "IE", "en-IE"),
    ("Turkey (TR)", "TR", "tr-TR"),
    ("United Arab Emirates (AE)", "AE", "ar-AE"),
    ("Saudi Arabia (SA)", "SA", "ar-SA"),
    ("Egypt (EG)", "EG", "ar-EG"),
    ("South Africa (ZA)", "ZA", "en-ZA"),
    ("India (IN)", "IN", "en-IN"),
    ("Japan (JP)", "JP", "ja-JP"),
    ("Australia (AU)", "AU", "en-AU"),
    ("Singapore (SG)", "SG", "en-SG"),
]

DEFAULT_MARKETPLACE_COUNTRY = "US"


def locale_for_country(country_code: str) -> str:
    """Looks up the Amplifi-style locale suffix for a country code, e.g.
    'DE' -> 'de-DE'. Raises ValueError if the country isn't in the list."""
    for _, code, locale in AMAZON_MARKETPLACES:
        if code == country_code:
            return locale
    raise ValueError(f"Unknown Amazon marketplace country code: {country_code!r}")


def marketplace_labels() -> list[str]:
    """Display labels in the fixed order above, for a selectbox."""
    return [label for label, _, _ in AMAZON_MARKETPLACES]


def country_for_label(label: str) -> str:
    """Reverses a dropdown label back to its country code."""
    for lbl, code, _ in AMAZON_MARKETPLACES:
        if lbl == label:
            return code
    raise ValueError(f"Unknown marketplace label: {label!r}")


def default_label() -> str:
    """The label for the default marketplace (US), to preselect in the UI."""
    for label, code, _ in AMAZON_MARKETPLACES:
        if code == DEFAULT_MARKETPLACE_COUNTRY:
            return label
    return AMAZON_MARKETPLACES[0][0]