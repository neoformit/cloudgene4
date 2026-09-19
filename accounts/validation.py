"""
Account field rules — the single source of truth (SPEC §3.4, issue A4).

The frontend mirrors these functions in ``frontend/src/utils/validation.js``. Both sides are
tested against the same table of examples, ``accounts/validation_cases.json``: when you change
a rule or message here, update that file and the JS module in the same commit.

Each ``validate_*`` function returns ``None`` when valid, else one human-readable message.
Inputs are normalised the same way the model normalises them before saving
(``normalize_username`` / ``normalize_email``).
"""
import re

USERNAME_MIN = 4
USERNAME_MAX = 150
USERNAME_RE = re.compile(r'^[A-Za-z0-9]+$')

EMAIL_MAX = 254
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

PASSWORD_MIN = 6
PASSWORD_MAX = 128

FULL_NAME_MAX = 255

GROUP_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')

MESSAGES = {
    'username_required': 'The username is required.',
    'username_short': 'The username must contain at least four characters.',
    'username_long': 'The username must not contain more than 150 characters.',
    'username_chars': 'Your username is not valid. Only characters A-Z, a-z and digits 0-9 are acceptable.',
    'email_required': 'E-Mail is required.',
    'email_long': 'The e-mail address is too long.',
    'email_invalid': 'Please enter a valid mail address.',
    'password_required': 'Password is required.',
    'password_mismatch': 'Please check your passwords.',
    'password_short': 'Password must contain at least six characters!',
    'password_long': 'Password must not contain more than 128 characters!',
    'password_digit': 'Password must contain at least one number (0-9)!',
    'password_lower': 'Password must contain at least one lowercase letter (a-z)!',
    'password_upper': 'Password must contain at least one uppercase letter (A-Z)!',
    'full_name_required': 'The full name is required.',
    'full_name_long': 'The full name must not contain more than 255 characters.',
    'group_name_invalid': ('Group names start with a letter or digit and contain only letters, '
                           'digits, "_", "-" and "." (max. 80 characters).'),
}


def normalize_username(value) -> str:
    return (value or '').strip()


def normalize_email(value) -> str:
    return (value or '').strip().lower()


def validate_username(value):
    value = normalize_username(value)
    if not value:
        return MESSAGES['username_required']
    if len(value) < USERNAME_MIN:
        return MESSAGES['username_short']
    if len(value) > USERNAME_MAX:
        return MESSAGES['username_long']
    if not USERNAME_RE.match(value):
        return MESSAGES['username_chars']
    return None


def validate_email(value):
    value = normalize_email(value)
    if not value:
        return MESSAGES['email_required']
    if len(value) > EMAIL_MAX:
        return MESSAGES['email_long']
    if not EMAIL_RE.match(value):
        return MESSAGES['email_invalid']
    return None


def validate_password(value, confirm=None):
    """Cloudgene rules: ≥6 characters with a digit, a lower- and an upper-case letter.

    ``confirm`` is only compared when given (clients may confirm locally).
    """
    value = value or ''
    if confirm is not None and value != confirm:
        return MESSAGES['password_mismatch']
    if not value:
        return MESSAGES['password_required']
    if len(value) < PASSWORD_MIN:
        return MESSAGES['password_short']
    if len(value) > PASSWORD_MAX:
        return MESSAGES['password_long']
    if not re.search(r'[0-9]', value):
        return MESSAGES['password_digit']
    if not re.search(r'[a-z]', value):
        return MESSAGES['password_lower']
    if not re.search(r'[A-Z]', value):
        return MESSAGES['password_upper']
    return None


def validate_full_name(value):
    value = (value or '').strip()
    if not value:
        return MESSAGES['full_name_required']
    if len(value) > FULL_NAME_MAX:
        return MESSAGES['full_name_long']
    return None


def validate_group_name(value):
    value = (value or '').strip()
    if not GROUP_NAME_RE.match(value):
        return MESSAGES['group_name_invalid']
    return None
