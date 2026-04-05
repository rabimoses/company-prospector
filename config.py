"""Configuration for company prospector."""

# Anthropic API
ANTHROPIC_API_KEY = "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"

# SERPER.DEV API Configuration
SERPER_API_KEY = "9a825cda6b2f831aa4d935f9a8dcabf22360b707"
SERPER_API_URL = "https://google.serper.dev/search"

# Improved search queries targeting specific news sources
# Using site: operators to find actual funding announcements and executive moves
SEARCH_QUERIES = [
    "raised Series B 2026 SaaS site:techcrunch.com",
    "raised Series C 2026 SaaS site:techcrunch.com",
    "appointed CRO 2026 B2B SaaS site:businesswire.com",
    "appointed Chief Revenue Officer 2026 site:prnewswire.com",
]

# Contact titles to search for — overridden at runtime by settings_manager
CONTACT_TITLES = [
    "CRO",
    "Chief Revenue Officer",
    "CMO",
    "Chief Marketing Officer",
    "CEO",
    "Co-Founder",
    "VP Marketing",
    "VP Demand Generation",
]

# Email signature
EMAIL_SIGNATURE = "Jacob Landsman"

# Telegram enabled (will check environment variables)
TELEGRAM_ENABLED = True

# Contact finding settings
MAX_CONTACTS_PER_COMPANY = 5

# Email opening templates
EMAIL_OPENING_TEMPLATES = {
    "funding": "Congrats on raising {amount}{round} — I saw that {company} just closed funding and wanted to reach out.",
    "cro_hire": "Welcome to {company}, {name}! I saw you just stepped into the CRO role and thought I'd reach out.",
    "headcount_growth": "I've been tracking {company}'s growth, and it's impressive to see the team scaling so quickly.",
}

# Default email parameters — overridden at runtime by settings_manager
def get_sender_info():
    from settings_manager import get_settings
    s = get_settings()
    return s["sender_name"], s["sender_title"]

SENDER_NAME = "Jacob Landsman"
SENDER_TITLE = "Demand Generation Leader"
