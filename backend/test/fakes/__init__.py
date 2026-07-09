"""Fakes and test doubles shared across the backend test suite."""

from test.fakes.auth import FakeAuthProvider, install_fake_auth, uninstall_fake_auth

__all__ = ["FakeAuthProvider", "install_fake_auth", "uninstall_fake_auth"]
