# Frontend Test Coverage

This page summarizes the frontend tests currently implemented.

| Area | What is covered | Test file |
| --- | --- | --- |
| Auth provider selection | Env validation, invalid values, caching, provider helpers, Keycloak config validation | frontend/__tests__/lib/auth/provider.test.ts |
| Provider-aware exports | Routing of token and user hooks based on provider selection | frontend/__tests__/lib/auth/provider-routing.test.ts |
| Provider-aware UI exports | UI component routing for Clerk vs Keycloak exports | frontend/__tests__/components/auth/providers/index.test.tsx |
| Clerk token handling | Authenticated vs unauthenticated, token fetch errors | frontend/__tests__/lib/auth/clerk-token.test.ts |
| Clerk user/org hooks | User parsing, org extraction, auth events | frontend/__tests__/lib/auth/clerk-hooks.test.ts |
| Keycloak token handling | Authenticated vs unauthenticated, refresh success/failure, external token path, error logging | frontend/__tests__/lib/auth/keycloak-token.test.ts |
| Keycloak user/org hooks | User parsing from claims, org extraction from azp/groups, auth events | frontend/__tests__/lib/auth/keycloak-hooks.test.ts |
| API wrapper | Auth headers, errors, streaming, URL cleaning, CRUD helper endpoints, auth header on write methods | frontend/__tests__/lib/api.test.ts |
| Keycloak auth buttons | Sign-in/up, user menu, signed-in/out wrappers, loading state, edge cases, login/register errors | frontend/__tests__/components/auth/providers/keycloak/AuthButtons.test.tsx |
| Keycloak login views | Login form states, auto-redirect, sign-up redirect | frontend/__tests__/components/auth/providers/keycloak/LoginForm.test.tsx |
| Keycloak provider root | Init success/failure, skip init, interval behavior, refresh warnings, loading UI | frontend/__tests__/components/auth/providers/keycloak/ProviderRoot.test.tsx |
| Organization manager | Loading, empty state, profile details, switcher, wrapper behavior | frontend/__tests__/components/auth/providers/keycloak/OrganizationManager.test.tsx |
| Proxy | Keycloak pass-through, Clerk delegation, token forwarding | frontend/__tests__/proxy.test.ts |
| Silent SSO asset | Public asset presence and postMessage script | frontend/__tests__/public/silent-check-sso.test.ts |
