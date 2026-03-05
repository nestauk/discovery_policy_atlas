"""Auth provider selection tests."""

import pytest


class TestAuthProviderSelection:
    """Tests for auth.py provider selection logic."""

    def test_missing_auth_provider_raises_error(self, monkeypatch):
        """Missing AUTH_PROVIDER env var raises ValueError."""
        monkeypatch.delenv("AUTH_PROVIDER", raising=False)

        # Need to reload the module to test import-time behavior
        import sys

        # Remove cached modules
        modules_to_remove = [
            k for k in sys.modules.keys() if k.startswith("app.core.auth")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        with pytest.raises(ValueError, match="AUTH_PROVIDER"):
            import app.core.auth  # noqa: F401

    def test_unsupported_provider_raises_error(self, monkeypatch):
        """Unsupported AUTH_PROVIDER raises NotImplementedError."""
        monkeypatch.setenv("AUTH_PROVIDER", "unsupported_provider")

        import sys

        modules_to_remove = [
            k for k in sys.modules.keys() if k.startswith("app.core.auth")
        ]
        for mod in modules_to_remove:
            del sys.modules[mod]

        with pytest.raises(NotImplementedError, match="unsupported_provider"):
            import app.core.auth  # noqa: F401
