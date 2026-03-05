# Frontend Testing Guide

This document describes the frontend testing setup, how to write tests, and best practices for maintaining test coverage.

## Overview

The frontend uses **Vitest** as the test runner with **React Testing Library** for component testing. Tests are located in the `frontend/__tests__/` directory, mirroring the structure of `lib/` and `components/`.

## Test Stack

- **Vitest** - Fast, Vite-native test runner
- **React Testing Library** - Testing utilities for React components
- **@testing-library/jest-dom** - Custom matchers for DOM assertions
- **@testing-library/user-event** - User interaction simulation
- **jsdom** - Browser-like DOM environment

## Available Commands

```bash
# Run all tests once
cd frontend
npm test

# Run tests in watch mode (for development)
npm run test:watch

# Run tests with coverage report
npm run test:coverage

# E2E tests placeholder (not yet configured)
npm run test:e2e
```

## Directory Structure

Tests are organized in `frontend/__tests__/` mirroring the source structure:

```markdown
frontend/
├── __tests__/
│   ├── lib/
│   │   ├── auth/
│   │   │   ├── provider.test.ts         # Provider selector tests
│   │   │   ├── provider-routing.test.ts # Provider-aware routing
│   │   │   ├── clerk-hooks.test.ts      # Clerk user/org hooks
│   │   │   ├── clerk-token.test.ts      # Clerk token acquisition
│   │   │   ├── keycloak-hooks.test.ts   # Keycloak useUser/useOrganization
│   │   │   └── keycloak-token.test.ts   # Keycloak token acquisition
│   │   └── api.test.ts                 # API wrapper tests
│   └── components/
│       └── auth/
│           └── providers/
│               ├── index.test.tsx
│               └── keycloak/
│                   ├── AuthButtons.test.tsx
│                   ├── LoginForm.test.tsx
│                   └── ProviderRoot.test.tsx
│   ├── proxy.test.ts
│   └── public/
│       └── silent-check-sso.test.ts
├── vitest.config.ts
└── vitest.setup.ts
```

## Writing Tests

### Basic Test Structure

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

describe('ComponentName', () => {
  beforeEach(() => {
    // Reset mocks, setup test state
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('describes what the test verifies', () => {
    render(<Component />);
    expect(screen.getByText('Expected text')).toBeInTheDocument();
  });
});
```

### Testing Hooks

```typescript
import { renderHook, waitFor } from '@testing-library/react';

describe('useCustomHook', () => {
  it('returns expected value', async () => {
    const { result } = renderHook(() => useCustomHook());
    
    await waitFor(() => {
      expect(result.current.value).toBe('expected');
    });
  });
});
```

### Mocking Modules

Use `vi.mock()` to mock dependencies:

```typescript
// Mock at the top of the file
vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
}));

// Define mock outside tests
const mockKeycloak = {
  authenticated: false,
  login: vi.fn(),
  // ...
};

// Reset in beforeEach
beforeEach(() => {
  mockKeycloak.authenticated = false;
  mockKeycloak.login = vi.fn();
});
```

### Testing with Environment Variables

Since env vars are read at module load time, reset modules between tests:

```typescript
const originalEnv = process.env;

beforeEach(() => {
  vi.resetModules();
  process.env = { ...originalEnv };
});

afterEach(() => {
  process.env = originalEnv;
});

it('works with clerk provider', async () => {
  process.env.NEXT_PUBLIC_AUTH_PROVIDER = 'clerk';
  
  // Dynamic import to pick up new env value
  const { getAuthProviderName } = await import('@/lib/auth/provider');
  expect(getAuthProviderName()).toBe('clerk');
});
```

### Testing User Interactions

```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

it('calls handler when button clicked', async () => {
  const user = userEvent.setup();
  const handleClick = vi.fn();
  
  render(<Button onClick={handleClick}>Click me</Button>);
  
  await user.click(screen.getByText('Click me'));
  expect(handleClick).toHaveBeenCalledTimes(1);
});
```

## Mocking Patterns

### Mocking the Keycloak Client

The Keycloak client is a singleton that needs careful mocking:

```typescript
const mockKeycloak = {
  authenticated: false,
  token: null as string | null,
  tokenParsed: null as Record<string, unknown> | null,
  login: vi.fn(),
  logout: vi.fn(),
  init: vi.fn().mockResolvedValue(true),
  updateToken: vi.fn().mockResolvedValue(true),
  // Event handlers
  onAuthSuccess: undefined,
  onAuthLogout: undefined,
};

vi.mock('@/lib/auth/providers/keycloak/client', () => ({
  getKeycloakInstance: () => mockKeycloak,
}));
```

### Mocking Fetch/API Calls

```typescript
const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

it('handles successful response', async () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ data: 'result' }),
  });
  
  const result = await fetchData();
  expect(result).toEqual({ data: 'result' });
});
```

### Mocking Next.js Router

The router is mocked in `vitest.setup.ts`:

```typescript
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));
```

## Coverage

Run `npm run test:coverage` to generate coverage reports. Reports are output in:

- `text` - Console output
- `json` - Machine-readable JSON
- `html` - Visual HTML report

Coverage includes `lib/**` and `components/**`, excluding test files.

For a detailed list of current coverage, see the Testing Coverage page:
[testing_coverage.md](testing_coverage.md)

## Best Practices

1. **Test behavior, not implementation** - Focus on what the component does, not how it does it.

2. **Use semantic queries** - Prefer `getByRole`, `getByLabelText` over `getByTestId`.

3. **Keep tests independent** - Each test should be able to run in isolation.

4. **Mock at the boundary** - Mock external dependencies (API, auth providers), not internal functions.

5. **Avoid testing implementation details** - Don't test internal state, test observable behavior.

6. **Write descriptive test names** - Use `it('does X when Y')` format.

7. **Cleanup mocks** - Always reset mocks in `beforeEach` or `afterEach`.

## E2E Testing (Future)

For end-to-end testing, Playwright is recommended. When configured:

```bash
# Run E2E tests
npm run test:e2e
```

E2E tests should cover:

- Full authentication flows (login, logout, token refresh)
- Critical user journeys
- Cross-browser compatibility

This is currently a placeholder command. See the [Playwright documentation](https://playwright.dev/) for setup instructions.

## Debugging Tests

### Run a single test file

```bash
npx vitest __tests__/lib/auth/provider.test.ts
```

### Run tests matching a pattern

```bash
npx vitest -t "handles authentication"
```

### Debug mode

```bash
npx vitest --ui
```

This opens the Vitest UI for interactive debugging.

## CI Integration

Tests run automatically in CI. Ensure:

- All tests pass before merging
- Coverage doesn't drop significantly
- No flaky tests (tests should be deterministic)
