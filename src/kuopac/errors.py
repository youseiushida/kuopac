"""Exception hierarchy."""
from __future__ import annotations


class KulineError(Exception):
    """Base exception for all kuopac errors."""


class NotFoundError(KulineError):
    """The requested bibid / ncid / blkey was not found."""


class ForbiddenError(KulineError):
    """KULINE returned 403 (usually due to a missing Referer header)."""


class CSRFError(KulineError):
    """Failed to obtain or use a CSRF token for a POST request."""


class ParseError(KulineError):
    """Server returned 200 but the HTML did not match the expected layout."""
