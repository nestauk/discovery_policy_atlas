import os

AUTH_PROVIDER = os.getenv("AUTH_PROVIDER")

if AUTH_PROVIDER is None:
    raise ValueError("AUTH_PROVIDER environment variable is not set.")

if not isinstance(AUTH_PROVIDER, str):
    raise TypeError("AUTH_PROVIDER must be a string.")

match provider := AUTH_PROVIDER.lower():
    case "clerk":
        from app.core.auth_providers.clerk import get_current_user  # noqa
    case "keycloak":
        from app.core.auth_providers.keycloak import get_current_user  # noqa
    case _:
        raise NotImplementedError(f"Unsupported AUTH_PROVIDER: {AUTH_PROVIDER}")
