import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

let mockOrganization: { id: string; name: string; slug?: string } | null = null;
let mockIsLoaded = true;

vi.mock('@/lib/auth/providers/keycloak/hooks', () => ({
  useOrganization: () => ({
    organization: mockOrganization,
    isLoaded: mockIsLoaded,
  }),
}));

const originalEnv = process.env;

beforeEach(() => {
  mockOrganization = null;
  mockIsLoaded = true;
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_PROVIDER: 'keycloak',
  };
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('OrganizationList', () => {
  it('shows loading state when not loaded', async () => {
    mockIsLoaded = false;

    const { OrganizationList } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    const { container } = render(<OrganizationList />);

    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when no organization', async () => {
    mockOrganization = null;

    const { OrganizationList } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(<OrganizationList />);

    expect(screen.getByText('No organization assigned.')).toBeInTheDocument();
  });

  it('renders organization name and group id when available', async () => {
    mockOrganization = { id: 'org-1', name: 'Policy Team', slug: 'policy-team' };

    const { OrganizationList } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(<OrganizationList />);

    expect(screen.getByText('Policy Team')).toBeInTheDocument();
    expect(screen.getByText('Group ID: policy-team')).toBeInTheDocument();
  });
});

describe('OrganizationSwitcher', () => {
  it('shows loading skeleton when not loaded', async () => {
    mockIsLoaded = false;

    const { OrganizationSwitcher } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    const { container } = render(<OrganizationSwitcher />);

    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('returns null when no organization', async () => {
    mockOrganization = null;

    const { OrganizationSwitcher } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    const { container } = render(<OrganizationSwitcher />);

    expect(container.firstChild).toBe(null);
  });

  it('renders organization name when available', async () => {
    mockOrganization = { id: 'org-2', name: 'Research Group', slug: 'research-group' };

    const { OrganizationSwitcher } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(<OrganizationSwitcher />);

    expect(screen.getByText('Research Group')).toBeInTheDocument();
  });
});

describe('OrganizationProfile', () => {
  it('shows empty state when no organization', async () => {
    mockOrganization = null;

    const { OrganizationProfile } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(<OrganizationProfile />);

    expect(screen.getByText('No organization profile available.')).toBeInTheDocument();
  });

  it('renders organization details when available', async () => {
    mockOrganization = { id: 'org-3', name: 'Insight Lab', slug: 'insight-lab' };

    const { OrganizationProfile } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(<OrganizationProfile />);

    expect(screen.getByText('Organization')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Insight Lab')).toBeInTheDocument();
    expect(screen.getByText('Group ID')).toBeInTheDocument();
    expect(screen.getByText('insight-lab')).toBeInTheDocument();
  });
});

describe('OrganizationManager', () => {
  it('renders list and children', async () => {
    mockOrganization = { id: 'org-4', name: 'Policy Ops', slug: 'policy-ops' };

    const { OrganizationManager } = await import('@/components/auth/providers/keycloak/OrganizationManager');
    render(
      <OrganizationManager>
        <div>Custom Child</div>
      </OrganizationManager>
    );

    expect(screen.getByText('Policy Ops')).toBeInTheDocument();
    expect(screen.getByText('Custom Child')).toBeInTheDocument();
  });
});
