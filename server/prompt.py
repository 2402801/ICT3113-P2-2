from categories import CATEGORIES

# The one classification prompt used for every candidate model. It is part of what is being
# measured: if any text here changes, bump PROMPT_VERSION and redo every official run.
PROMPT_VERSION = "v1"

# Scope notes condensed from labelling protocol v3, section 1 (category definitions only).
# The section 2-3 decision order and edge-case rules are deliberately left out, so the model is
# classifying zero-shot from definitions, as assumed in the prediction record.
CATEGORY_SCOPE = {
    "Credit reporting": "what is on the consumer's credit report/file itself: accuracy, an "
    "investigation, or a dispute with a credit bureau (Equifax, Experian, TransUnion) or with "
    "how a lender reports the account",
    "Debt collection": "being pursued for a debt: calls, letters, threats, demands, debt "
    "validation requests, 'this debt isn't mine', harassment; the debt can come from any product",
    "Mortgage": "a home loan: origination, servicing, escrow, modification, foreclosure, "
    "refinancing, payment processing, release of a satisfied lien",
    "Credit card": "the cardholder relationship with the card issuer: billing disputes, "
    "unauthorized charges, APR/interest, rewards, account closure, fraud on the card",
    "Bank account or service": "checking/savings accounts and general bank services: deposits, "
    "holds, overdraft, account closure, fraud on the account, customer service, ATM problems",
    "Consumer loan": "non-mortgage installment credit: personal loans, auto loans, student "
    "loans, payday loans",
    "Money transfer or service": "moving money between parties: P2P apps (Zelle, Venmo, Cash "
    "App), wire transfers, remittances, prepaid cards, money orders",
}

assert set(CATEGORY_SCOPE) == set(CATEGORIES), "prompt categories must match categories.py"

_HEADER = (
    "You route customer complaint tickets for a financial services company.\n"
    "Classify the complaint into exactly one of these seven categories:\n\n"
    + "\n".join(f"- {name}: {CATEGORY_SCOPE[name]}" for name in CATEGORIES)
    + "\n\nAnswer with JSON only, in exactly this form: {\"category\": \"<category name>\"}\n"
    "The category name must be one of the seven names above, written exactly as shown.\n\n"
    'Complaint:\n"""\n'
)
_FOOTER = '\n"""'


def build_prompt(narrative: str) -> str:
    return _HEADER + narrative + _FOOTER
