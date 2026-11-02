"""Message language packs, independent of the future UI translation locale.

Add a pack and provider fixtures to support another message language. Unsupported
templates remain for review rather than guessing from a generic thank-you.
"""
from dataclasses import dataclass
from datetime import date
import re
import unicodedata


def normalized(value):
    value = ''.join(' ' if unicodedata.category(char).startswith('P') else char for char in (value or ''))
    value = unicodedata.normalize('NFKC', value).casefold()
    value = ''.join(''.join(part for part in unicodedata.normalize('NFKD', char)
                            if not unicodedata.combining(part))
                    if 'LATIN' in unicodedata.name(char, '') else char for char in value)
    return re.sub(r'[\W_]+', ' ', value).strip()


@dataclass(frozen=True)
class LanguagePack:
    code: str
    sent_prefix: str
    sent_to: str
    linkedin_prefix: str
    confirmations: tuple[str, ...]
    freework: tuple[str, ...]
    rejections: tuple[str, ...]
    interviews: tuple[str, ...]
    update_markers: tuple[str, ...]
    applied_date: str
    months: tuple[str, ...]
    search: tuple[str, ...]


LANGUAGES = (
    LanguagePack(
        code='en', sent_prefix=r'Application submitted',
        sent_to=r'The following items were sent to (.+?)\. Good luck',
        linkedin_prefix=r'Your application was sent to ',
        confirmations=(r"(?:thank(?:s| you)(?: very much)? for applying|thank you for your application) (?:for|to)(?: the (?:position|role) of)?\s+(.+?)\s+(?:at|with)\s+(.+?)(?:[.!](?=\s|Unfortunately|$)|$)",),
        freework=(r'Your application for (?:the (?:position|role)(?: of)? )?(.+?) (?:at|with) (.+?) (?:has been|was) (?:successfully )?(?:sent|submitted|received)\b',),
        rejections=(r'\b(?:decided not to (?:proceed|move forward) with your application|your application (?:has been|was) unsuccessful|you have not been selected|your application (?:was not|has not been) selected|we regret to inform you .{0,100}(?:not selected|unsuccessful)|we have decided to (?:pursue|proceed with) other candidates)\b',),
        interviews=(r'\b(?:invite you to (?:an? )?(?:interview|technical interview)|we would like to schedule (?:an? )?interview)\b',),
        update_markers=(r'\b(?:unfortunately|not (?:been )?selected)\b',),
        applied_date=r'Applied on (?P<month>[A-Za-z]+) (?P<day>\d{1,2}),? (?P<year>\d{4})',
        months=('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'),
        search=('application', 'interview'),
    ),
    LanguagePack(
        code='fr', sent_prefix=r'Candidature envoyée',
        sent_to=r'Les éléments suivants ont été envoyés à (.+?)\. Bonne chance',
        linkedin_prefix=r'Votre candidature a été (?:envoyée|transmise) à ',
        confirmations=(r"(?:merci (?:d['’]avoir postulé|pour votre candidature)|nous vous remercions (?:d['’]avoir postulé|pour votre candidature)) (?:pour|au)(?: (?:le )?poste(?: de)?)?\s+(.+?)\s+(?:chez|au sein de)\s+(.+?)(?:[.!](?=\s|Malheureusement|$)|$)",),
        freework=(r"Votre candidature (?:pour|au) (?:le )?(?:poste (?:de )?)?(.+?) (?:chez|au sein de) (.+?) a (?:bien )?été (?:envoyée|transmise|reçue)\b",),
        rejections=(r'\b(?:candidature n a pas ete retenue|ne donnerons pas (?:une )?suite (?:favorable )?a votre candidature|votre candidature n est pas retenue|nous ne pouvons pas donner une suite favorable a votre candidature)\b',),
        interviews=(r'\b(?:nous vous invitons a (?:un |une )?(?:entretien|rencontre)|nous souhaitons vous rencontrer (?:pour|lors d) un entretien)\b',),
        update_markers=(r'\bmalheureusement\b',),
        applied_date=r'(?:Candidature (?:envoyée|transmise)|Postulé) le (?P<day>\d{1,2}) (?P<month>[\wéû]+) (?P<year>\d{4})',
        months=('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'),
        search=('candidature', 'postulé', '"CV a été envoyé"', 'entretien'),
    ),
)


def lifecycle(text):
    text = normalized(text)
    rejected = [p.code for p in LANGUAGES if any(re.search(pattern, text) for pattern in p.rejections)]
    invited = [p.code for p in LANGUAGES if any(re.search(pattern, text) for pattern in p.interviews)]
    # Contradictory current-body statements must remain a human decision.
    if rejected and invited:
        return {}, None
    if rejected:
        return {'status': 'CLOSED', 'outcome': 'UNSUCCESSFUL'}, rejected[0]
    if invited:
        return {'status': 'INTERVIEW'}, invited[0]
    return {}, None


def applied_date(text):
    for pack in LANGUAGES:
        found = re.search(pack.applied_date, text, re.I)
        if not found:
            continue
        month = normalized(found['month'])
        candidates = [i + 1 for i, name in enumerate(pack.months)
                      if normalized(name) == month or normalized(name)[:3] == month]
        if len(candidates) == 1:
            try:
                return date(int(found['year']), candidates[0], int(found['day'])).isoformat()
            except ValueError:
                pass
    return None


def has_update_signals(text):
    text = normalized(text)
    return any(re.search(pattern, text) for pack in LANGUAGES
               for pattern in (*pack.rejections, *pack.interviews, *pack.update_markers))


def search_terms():
    """Expand candidate retrieval vocabulary together with supported languages."""
    return tuple(dict.fromkeys(term for pack in LANGUAGES for term in pack.search))
