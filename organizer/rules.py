"""Rule-based email classification — zero API cost.

Categories: Important, Personal, Receipts, Promotions, Junk
"""

import logging
import re

from organizer.utils import extract_domain, extract_email

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protected email detection
# ---------------------------------------------------------------------------

_PROTECTED_DOMAINS: frozenset = frozenset({
    "masuk.org", "masukhs.org",
    "monroe.ct.us", "monroect.org",
    "asu.edu", "on.asu.edu", "reply.asu.edu", "s.asu.edu",
    "monroe.k12.ct.us",
})

# Covers subdomains: alumni.masukhs.org, mail.masuk.org, etc.
_PROTECTED_DOMAIN_SUFFIXES: tuple = (
    ".monroe.ct.us", ".monroect.org",
    ".asu.edu",
    ".masuk.org", ".masukhs.org",
)

_PROTECTED_KW: re.Pattern = re.compile(
    r"\b(masuk|masukhs|"
    r"monroe\s*ct|monroe\s*connecticut|"
    r"stepney|stevenson|"
    r"town\s+of\s+monroe|monroe\s+public\s+schools|"
    r"mhs|panthers|"
    r"arizona\s+state(\s+university)?|asu|"
    r"graduation|transcript|enrollment|financial\s+aid|"
    r"student\s+loans?|fafsa|gpa|grade\s+point|"
    r"academic\s+(record|standing|probation|calendar)|"
    r"course\s+(registration|schedule|drop|add)|"
    r"professors?|semester|tuition)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Domain sets
# ---------------------------------------------------------------------------

_VIP_DOMAINS: frozenset = frozenset({"meadeengineering.com"})

_PERSONAL_DOMAINS: frozenset = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "aol.com", "protonmail.com", "mail.com",
    "zoho.com", "ymail.com", "live.com", "msn.com", "me.com",
    "pm.me", "proton.me", "fastmail.com", "hey.com", "mac.com",
})

_RECEIPT_DOMAINS: frozenset = frozenset({
    "amazon.com", "amazon.co.uk", "doordash.com", "ubereats.com",
    "paypal.com", "venmo.com", "squareup.com", "stripe.com",
    "etsy.com", "ebay.com", "walmart.com", "target.com",
    "bestbuy.com", "costco.com", "apple.com",
    "grubhub.com", "postmates.com", "instacart.com",
    "shopify.com", "ups.com", "fedex.com", "usps.com", "dhl.com",
    "shipbob.com", "shipstation.com",
})

_PROMO_ESP_DOMAINS: frozenset = frozenset({
    "substack.com", "mailchimp.com", "sendgrid.net",
    "constantcontact.com", "campaignmonitor.com", "hubspot.com",
    "mailgun.org", "sendinblue.com", "brevo.com", "convertkit.com",
    "beehiiv.com", "buttondown.email", "getresponse.com", "drip.com",
    "aweber.com", "keap-mail.com", "klaviyo.com", "listrak.com",
    "sailthru.com", "marketo.net", "em.linkedin.com",
    "facebookmail.com",
})

_PROMO_BRAND_DOMAINS: frozenset = frozenset({
    "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "pinterest.com", "reddit.com", "redditmail.com", "tumblr.com",
    "snapchat.com", "discord.com", "quora.com", "nextdoor.com",
    "youtube.com", "twitch.tv", "groupon.com", "retailmenot.com",
    "uber.com", "messages.doordash.com",
    "customermail.microsoft.com", "email.bestbuy.com",
    "hello.klarna.com", "trulieve.com", "varomoney.com",
    "hushloungeaz.com", "advocate.uhc.com", "m.starbucks.com",
    "marketing.mlbemail.com", "d.email.draftkings.com",
    "marketing.thescore.bet", "updates.bandsintown.com",
    "tickpick.com", "tdgarden-email.com",
})

_AUTOMATED_LOCALS: frozenset = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications", "notification", "mailer-daemon", "postmaster",
    "auto-confirm", "automated", "system", "alerts", "alert",
    "security", "account", "accounts", "digest", "bounce", "bounces",
    "news", "updates", "newsletter", "mailer", "unsubscribe",
    "no.reply", "do.not.reply",
})

_GENERIC_LOCALS: frozenset = frozenset({
    "hello", "team", "billing", "support", "info", "admin",
    "contact", "help", "sales", "marketing", "feedback",
    "webmaster", "hostmaster", "abuse", "privacy", "service",
    "care", "reply", "mail", "email", "office", "enquiries",
})

# ---------------------------------------------------------------------------
# Keyword patterns
# ---------------------------------------------------------------------------

_RECEIPT_SUBJ: re.Pattern = re.compile(
    r"\b(receipt|order\s+confirm|purchase\s+confirm|"
    r"payment\s+confirm|"
    r"transaction\s+receipt|your\s+order|order\s*#|"
    r"order\s+shipped|has\s+shipped|delivery\s+confirm|"
    r"package\s+delivered|shipment|tracking\s+number|"
    r"digital\s+receipt|payment\s+received|charge\s+of)",
    re.IGNORECASE,
)

# Strong billing signals that must beat receipt matching
# (e.g. "Payment Due: Invoice #" is not a receipt)
_BILLING_OVERRIDE: re.Pattern = re.compile(
    r"\b(payment\s+due|past\s+due|overdue|amount\s+due|"
    r"bill\s+due|invoice\s+due|balance\s+due|"
    r"action\s+required|urgent|account\s+suspended|"
    r"final\s+(notice|warning)|immediately)\b",
    re.IGNORECASE,
)

_PROMO_SUBJ: re.Pattern = re.compile(
    r"(\d+\s*%\s*off|\bsale\b|\bdeal\b|coupon|discount|"
    r"free\s+shipping|"
    r"limited\s+time|exclusive\s+offer|don.t\s+miss|last\s+chance|"
    r"flash\s+sale|clearance|save\s+\$|bogo|promo\s+code|"
    r"special\s+offer|act\s+now|ends\s+(soon|today|tonight)|"
    r"just\s+for\s+you|shop\s+now|buy\s+now)",
    re.IGNORECASE,
)

_NEWSLETTER_SUBJ: re.Pattern = re.compile(
    r"\b(newsletter|digest|weekly|daily\s+briefing|roundup|"
    r"this\s+week\s+in|top\s+stories|issue\s+#?\d+|edition|recap)\b",
    re.IGNORECASE,
)

_IMPORTANT_SUBJ: re.Pattern = re.compile(
    r"\b(invoice|payment\s+due|past\s+due|overdue|bill\s+due|"
    r"contract|agreement|legal\s+notice|lawsuit|court\b|"
    r"appointment|interview|meeting\s+request|"
    r"urgent\b|action\s+required|immediate\s+action|\basap\b|"
    r"deadline|expir(es?|ing)|renewal|renew\s+now|"
    r"offer\s+letter|job\s+offer|acceptance\b|"
    r"account\s+(suspended|locked|compromised)|"
    r"suspicious\s+activity|fraud\s+alert|"
    r"\btax\s+(return|document|form|filing)\b|\birs\b|w.2\b|1099\b|"
    r"insurance\s+(claim|policy|renewal)|"
    r"medical\b|prior\s+auth)\b",
    re.IGNORECASE,
)

_SECURITY_CODE: re.Pattern = re.compile(
    r"\b(verification\s+code|security\s+code|"
    r"one.?time\s+(password|code)|"
    r"\botp\b|your\s+code\s+is|login\s+code|sign.?in\s+code|"
    r"2fa\b|two.factor|authentication\s+code|access\s+code)\b",
    re.IGNORECASE,
)

_SOCIAL_NOTIF: re.Pattern = re.compile(
    r"\b(liked\s+your|commented\s+on|mentioned\s+you|tagged\s+you|"
    r"new\s+follower|friend\s+request|connection\s+request|"
    r"accepted\s+your|shared\s+a\s+post|invited\s+you|"
    r"reacted\s+to|pinged\s+you)\b",
    re.IGNORECASE,
)

_IMPORTANCE_SIGNAL: re.Pattern = re.compile(
    r"\b(invoice|payment\s+due|urgent\b|action\s+required|"
    r"deadline|appointment|contract|offer\s+letter|renewal|"
    r"your\s+account|verify|confirm\s+your|past\s+due|overdue|"
    r"expir(es?|ing)|suspicious|fraud)\b",
    re.IGNORECASE,
)

# Urgency keywords for triage scoring — precompiled for performance.
# Compiled once at module load; re-use avoids per-email recompilation.
URGENCY_KEYWORDS: list = [
    "invoice", "payment due", "urgent", "action required",
    "deadline", "appointment", "contract", "offer", "renewal",
]
_URGENCY_PATTERNS: list = [
    re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    for kw in URGENCY_KEYWORDS
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_protected(subject: str, sender: str, snippet: str = "") -> bool:
    """Return True if this email must only get a Saved label.

    Protected emails (school, Monroe CT, ASU) are never archived or
    deleted under any circumstances.

    Args:
        subject: Email subject line.
        sender: From header value.
        snippet: Optional email body preview snippet.

    Returns:
        True if the email matches a protected domain or keyword.
    """
    domain = extract_domain(sender)

    if domain in _PROTECTED_DOMAINS:
        return True
    if any(domain.endswith(sfx) for sfx in _PROTECTED_DOMAIN_SUFFIXES):
        return True

    return bool(_PROTECTED_KW.search(f"{subject} {snippet}"))


def is_important_signal(  # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    subject: str,
    sender: str,
    snippet: str,
    age_days: float,
    is_unread: bool,
    replied_to: bool,
) -> bool:
    """Return True if this email should get 'Review Me' instead of deletion.

    Args:
        subject: Email subject line.
        sender: From header value.
        snippet: Email body preview snippet.
        age_days: Message age in days.
        is_unread: True if the UNREAD label is present.
        replied_to: True if the account has previously replied to sender.

    Returns:
        True if any importance signal is detected.
    """
    local = _local(sender)
    domain = extract_domain(sender)

    if _is_real_person(local, domain):
        return True
    if (
        _IMPORTANCE_SIGNAL.search(subject)
        or _IMPORTANCE_SIGNAL.search(snippet)
    ):
        return True
    # Unread and young: user may not have seen it yet.
    if is_unread and age_days < 90:
        return True
    if replied_to:
        return True
    return False


def classify_email(  # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    # pylint: disable=too-many-return-statements,too-many-branches
    subject: str,
    sender: str,
    snippet: str,
    has_unsubscribe: bool,
    gmail_labels: list,
    replied_to: bool = False,
) -> str:
    """Classify an email into one of five categories.

    Categories: Important, Personal, Receipts, Promotions, Junk.

    Args:
        subject: Email subject line.
        sender: From header value.
        snippet: Email body preview snippet.
        has_unsubscribe: True if a List-Unsubscribe header is present.
        gmail_labels: List of Gmail label ID strings on the message.
        replied_to: True if the account has previously replied to sender.

    Returns:
        One of: ``"Important"``, ``"Personal"``, ``"Receipts"``,
        ``"Promotions"``, or ``"Junk"``.
    """
    domain = extract_domain(sender)
    local = _local(sender)
    text = f"{subject} {snippet}"

    # VIP / protected domains → Important
    if domain in _VIP_DOMAINS:
        return "Important"
    if domain in _PROTECTED_DOMAINS or any(
        domain.endswith(sfx) for sfx in _PROTECTED_DOMAIN_SUFFIXES
    ):
        return "Important"

    # Security / OTP codes → Junk (automated, ephemeral)
    if _SECURITY_CODE.search(subject):
        return "Junk"

    # Strong billing signals beat receipt matching
    # ("Payment Due: Invoice #" is not a receipt)
    if _BILLING_OVERRIDE.search(subject):
        return "Important"

    # Receipt signals (order confirmations, shipping, payment receipts)
    if _RECEIPT_SUBJ.search(subject):
        return "Receipts"
    if domain in _RECEIPT_DOMAINS and _RECEIPT_SUBJ.search(text):
        return "Receipts"

    # Important signals (bills, contracts, appointments, etc.)
    if _IMPORTANT_SUBJ.search(subject):
        return "Important"

    # Social activity notifications → Junk
    if _SOCIAL_NOTIF.search(subject):
        return "Junk"

    # Known email service provider / promo brand domains → Promotions
    if domain in _PROMO_ESP_DOMAINS or domain in _PROMO_BRAND_DOMAINS:
        return "Promotions"

    # List-Unsubscribe header is a reliable bulk/marketing signal
    if has_unsubscribe:
        return "Promotions"

    # Newsletter or promo patterns in subject/snippet
    if _NEWSLETTER_SUBJ.search(text) or _PROMO_SUBJ.search(subject):
        return "Promotions"

    # Gmail's own category tabs
    if any(
        label in gmail_labels
        for label in (
            "CATEGORY_PROMOTIONS",
            "CATEGORY_SOCIAL",
            "CATEGORY_FORUMS",
        )
    ):
        return "Promotions"

    # Replied-to real person (sender we've emailed before and looks human)
    if replied_to and _is_real_person(local, domain):
        return "Personal"

    # Automated / noreply sender → Junk
    if _is_automated(local, domain):
        return "Junk"

    # Personal email domains (gmail, yahoo, etc.) → Personal
    if domain in _PERSONAL_DOMAINS:
        return "Personal"

    # Real person heuristic (firstname.lastname pattern) → Personal
    if _is_real_person(local, domain):
        return "Personal"

    # Gmail marks as Primary → Personal
    if "CATEGORY_PERSONAL" in gmail_labels:
        return "Personal"

    # Domain with automated-looking name → Junk
    if _auto_domain(domain):
        return "Junk"

    return "Promotions"


def score_priority(  # pylint: disable=too-many-arguments
    # pylint: disable=too-many-positional-arguments
    subject: str,
    sender: str,
    is_unread: bool,
    age_days: float,
    replied_to: bool,
    gmail_labels: list,
) -> int:
    """Score an email 1–10 for triage ranking (higher = more urgent).

    Args:
        subject: Email subject line.
        sender: From header value.
        is_unread: True if the UNREAD label is present.
        age_days: Message age in days.
        replied_to: True if the account has previously replied to sender.
        gmail_labels: List of Gmail label ID strings on the message.

    Returns:
        Integer score in the range [1, 10].
    """
    local = _local(sender)
    domain = extract_domain(sender)
    score = 0

    # +3 if sender is a real person
    if _is_real_person(local, domain):
        score += 3

    # +2 per urgency keyword match in subject (contribution capped at 6)
    hits = sum(
        1 for pattern in _URGENCY_PATTERNS if pattern.search(subject)
    )
    score += min(hits * 2, 6)

    # +1 if unread
    if is_unread:
        score += 1

    # +2 if < 7 days old
    if age_days < 7:
        score += 2

    # +2 if sender has been replied to before
    if replied_to:
        score += 2

    # +1 if not in Promotions/Social/Forums tab (landed in Primary)
    if not any(
        label in gmail_labels
        for label in (
            "CATEGORY_PROMOTIONS",
            "CATEGORY_SOCIAL",
            "CATEGORY_FORUMS",
        )
    ):
        score += 1

    return max(1, min(score, 10))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _local(sender: str) -> str:
    """Extract the local part (before @) of a sender address.

    Args:
        sender: Raw From header value.

    Returns:
        Lowercase local-part string, or empty string if no @ found.
    """
    email = extract_email(sender)
    return email.split("@")[0] if "@" in email else ""


def _is_automated(local: str, domain: str = "") -> bool:
    """Return True if the local part or domain looks automated/noreply.

    Args:
        local: Local part of the sender's email address.
        domain: Domain part of the sender's email address.

    Returns:
        True if the sender appears to be an automated system.
    """
    local_lower = local.lower()
    if local_lower in _AUTOMATED_LOCALS:
        return True
    if any(
        local_lower.startswith(prefix)
        for prefix in (
            "noreply", "no-reply", "donotreply",
            "notification", "automated", "auto-",
            "bounce", "mailer",
        )
    ):
        return True
    if "noreply" in domain or "no-reply" in domain:
        return True
    return False


def _is_real_person(local: str, domain: str) -> bool:
    """Return True if the sender looks like a real individual.

    Args:
        local: Local part of the sender's email address.
        domain: Domain part of the sender's email address.

    Returns:
        True if the sender is likely a real person.
    """
    if _is_automated(local, domain):
        return False
    if local in _GENERIC_LOCALS:
        return False
    # Personal domain + non-generic local = almost certainly a real person
    if domain in _PERSONAL_DOMAINS:
        return True
    # firstname.lastname or first_last pattern common in corporate email
    if re.match(r"^[a-z]{2,15}[._-][a-z]{2,15}\d{0,3}$", local.lower()):
        return True
    return False


def _auto_domain(domain: str) -> bool:
    """Return True if the domain name itself contains automation markers.

    Args:
        domain: Domain string to check.

    Returns:
        True if the domain contains an automated-sender pattern.
    """
    for pattern in (
        "notification", "alert", "noreply", "no-reply",
        "mailer", "automated",
    ):
        if pattern in domain:
            return True
    return False
