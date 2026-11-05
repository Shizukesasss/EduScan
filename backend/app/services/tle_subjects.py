"""Recognize typed TLE specializations without changing subject identities."""
import re
import unicodedata


def tle_specialization(name: str) -> str | None:
    name = ' '.join((name or '').split())
    if name.upper() in {'TLE', 'TECHNOLOGY AND LIVELIHOOD EDUCATION'}:
        return ''
    match = re.fullmatch(r'TLE\s*-\s*(.*)', name, flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def tle_name_key(name: str) -> str | None:
    specialization = tle_specialization(name)
    return unicodedata.normalize('NFC', specialization).casefold() if specialization is not None else None


def tle_code_base(specialization: str) -> str:
    slug = re.sub(r'[^A-Z0-9]+', '-', specialization.upper()).strip('-') or 'SPECIALIZATION'
    return f'TLE-{slug}'[:40].rstrip('-')
