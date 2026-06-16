"""Authentication package.

Public surface stays small on purpose: routes only need ``get_current_user``
and ``CurrentUser``. Provider implementations and the factory are internal
details.
"""

from app.core.auth.base import AuthError, AuthProvider, CurrentUser, ProviderClaims
from app.core.auth.dependencies import get_current_user
from app.core.auth.factory import get_auth_provider
from app.core.auth.identity import InternalIdentity, find_or_provision

__all__ = [
    "AuthError",
    "AuthProvider",
    "CurrentUser",
    "InternalIdentity",
    "ProviderClaims",
    "find_or_provision",
    "get_auth_provider",
    "get_current_user",
]
