"""Free-text expense parser.

Turns whatever you actually type into a Telegram chat into a structured
expense. Deliberately order-agnostic: the amount can appear anywhere, and
the category can appear anywhere, because nobody types in a fixed order at
11pm after dinner.

    "250 food dinner"        -> 250.00 / Food     / "dinner"
    "dinner 250"             -> 250.00 / Food     / "dinner"
    "paid rs 1,250 for uber" -> 1250.00 / Transport / "paid for uber"
    "1.2k rent"              -> 1200.00 / Rent     / ""
    "300"                    -> 300.00 / Uncategorized / ""
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

# Canonical category -> words that should map to it. First match wins, so
# order the map from most specific to most generic.
CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Food": (
        "food", "lunch", "dinner", "breakfast", "brunch", "snack", "snacks",
        "restaurant", "cafe", "coffee", "tea", "chai", "swiggy", "zomato",
        "eat", "eating", "meal", "canteen", "tiffin", "zepto", "blinkit",
    ),
    "Groceries": (
        "grocery", "groceries", "vegetables", "veggies", "sabzi", "milk",
        "bigbasket", "dmart", "supermarket", "kirana", "provisions",
    ),
    "Transport": (
        "transport", "travel", "uber", "ola", "rapido", "cab", "taxi", "auto",
        "metro", "bus", "train", "flight", "fuel", "petrol", "diesel",
        "parking", "toll", "rickshaw",
    ),
    "Rent": ("rent", "landlord", "maintenance", "society", "brokerage"),
    "Utilities": (
        "utilities", "utility", "electricity", "power", "water", "gas",
        "internet", "wifi", "broadband", "mobile", "recharge", "phone", "bill",
    ),
    "Health": (
        "health", "medical", "medicine", "medicines", "pharmacy", "chemist",
        "doctor", "hospital", "clinic", "dentist", "gym", "insurance",
    ),
    "Shopping": (
        "shopping", "clothes", "clothing", "shoes", "amazon", "flipkart",
        "myntra", "electronics", "gadget", "furniture", "ikea",
    ),
    "Entertainment": (
        "entertainment", "movie", "movies", "cinema", "pvr", "netflix",
        "spotify", "prime", "hotstar", "game", "games", "concert", "bar",
        "drinks", "party", "subscription",
    ),
    "Education": (
        "education", "book", "books", "course", "tuition", "fees", "school",
        "college", "udemy", "coursera",
    ),
    "Personal": (
        "personal", "salon", "haircut", "grooming", "spa", "cosmetics",
        "laundry", "dryclean",
    ),
    "Gifts": ("gift", "gifts", "donation", "charity", "temple", "shagun"),
    "Home": ("home", "househelp", "maid", "cook", "repair", "plumber", "electrician"),
    "Investment": ("investment", "invest", "sip", "mutual", "stocks", "fd", "ppf", "nps"),
    "Travel": ("trip", "hotel", "airbnb", "vacation", "holiday", "booking"),
}

# Flat lookup built once at import.
_WORD_TO_CATEGORY: dict[str, str] = {
    word: category
    for category, words in CATEGORY_SYNONYMS.items()
    for word in words
}

DEFAULT_CATEGORY = "Uncategorized"

# Currency noise that should never end up in the description.
_NOISE_WORDS = frozenset({
    "rs", "rs.", "inr", "rupees", "rupee", "for", "on", "at", "spent", "paid",
    "of", "the", "a", "an", "to", "was", "is", "cost", "costs", "bought",
})

# Matches: 250 | 250.50 | 1,250 | ₹250 | rs250 | 1.2k | 2k
_AMOUNT_RE = re.compile(
    r"""
    (?:^|(?<=[\s₹$rs.]))          # start, or after whitespace/currency noise
    (?:₹|rs\.?|inr|\$)?\s*        # optional currency prefix
    (\d{1,3}(?:,\d{2,3})+|\d+)    # 1,23,456 / 1,234 / 250
    (?:\.(\d{1,2}))?              # optional paise
    \s*(k|l|lakh|lac)?            # optional multiplier suffix
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MULTIPLIERS = {"k": 1_000, "l": 100_000, "lakh": 100_000, "lac": 100_000}

# Relative-date words the parser understands, mapped to a day offset.
_DATE_WORDS = {"today": 0, "yday": -1, "yesterday": -1, "dby": -2}


class ParseError(ValueError):
    """Raised when the message contains no usable amount."""


@dataclass(frozen=True)
class ParsedExpense:
    amount: float
    category: str
    description: str
    spent_on: date
    raw_message: str
    matched_keyword: str | None = field(default=None)

    @property
    def is_categorized(self) -> bool:
        return self.category != DEFAULT_CATEGORY


def _extract_amount(text: str) -> tuple[float, tuple[int, int]]:
    """Return (amount, (start, end)) for the first plausible amount."""
    for match in _AMOUNT_RE.finditer(text):
        whole, paise, suffix = match.group(1), match.group(2), match.group(3)
        value = float(whole.replace(",", ""))
        if paise:
            value += float(f"0.{paise}")
        if suffix:
            value *= _MULTIPLIERS[suffix.lower()]
        if value <= 0:
            continue
        return round(value, 2), match.span()
    raise ParseError("no amount found")


def _tokenize(text: str) -> list[str]:
    # Deliberately does NOT split on "/": that would mangle "1/2 kg", dates
    # like "9/8", and any stray markup the user types.
    return [t for t in re.split(r"[\s,;:|]+", text) if t]


def _category_for(token: str) -> str | None:
    """Look up a token, tolerating plurals and glued forms like 'food/drinks'."""
    for part in re.split(r"[/&+]", token):
        part = part.strip()
        if not part:
            continue
        hit = _WORD_TO_CATEGORY.get(part) or _WORD_TO_CATEGORY.get(part.rstrip("s"))
        if hit:
            return hit
    return None


def parse_expense(message: str, *, today: date | None = None) -> ParsedExpense:
    """Parse a raw Telegram message into a ParsedExpense.

    Raises ParseError if no amount can be found.
    """
    raw = (message or "").strip()
    if not raw:
        raise ParseError("empty message")

    today = today or date.today()
    amount, (start, end) = _extract_amount(raw)

    # Everything except the amount is candidate category/description text.
    remainder = f"{raw[:start]} {raw[end:]}".strip()

    category = DEFAULT_CATEGORY
    matched_keyword: str | None = None
    spent_on = today
    description_tokens: list[str] = []

    for token in _tokenize(remainder):
        key = token.lower().strip(".!?'\"()")
        if not key:
            continue

        if key in _DATE_WORDS:
            spent_on = today + timedelta(days=_DATE_WORDS[key])
            continue

        if category == DEFAULT_CATEGORY:
            hit = _category_for(key)
            if hit:
                category, matched_keyword = hit, key
                # Drop the keyword from the description only when it just
                # restates the category ("food" -> Food). Keep genuinely
                # informative ones: "uber" -> Transport still means uber.
                if key.rstrip("s") != hit.lower().rstrip("s"):
                    description_tokens.append(token)
                continue

        if key in _NOISE_WORDS:
            continue

        description_tokens.append(token)

    description = " ".join(description_tokens).strip(" -–—")

    return ParsedExpense(
        amount=amount,
        category=category,
        description=description,
        spent_on=spent_on,
        raw_message=raw,
        matched_keyword=matched_keyword,
    )


def format_amount(value: float, symbol: str = "₹") -> str:
    """₹1,250 — drop the decimals when they are .00, keep them otherwise."""
    if float(value).is_integer():
        return f"{symbol}{value:,.0f}"
    return f"{symbol}{value:,.2f}"
