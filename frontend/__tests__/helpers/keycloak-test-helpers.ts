export type KeycloakCoreMock = {
  authenticated?: boolean;
  token: string | null;
  tokenParsed: Record<string, unknown> | null;
  onAuthSuccess?: (() => void) | undefined;
  onAuthLogout?: (() => void) | undefined;
  onAuthRefreshSuccess?: (() => void) | undefined;
  onAuthRefreshError?: (() => void) | undefined;
};

export function makeKeycloakEnv(
  originalEnv: NodeJS.ProcessEnv
): NodeJS.ProcessEnv {
  return {
    ...originalEnv,
    NEXT_PUBLIC_AUTH_PROVIDER: 'keycloak',
  };
}

export function resetKeycloakCore(mockKeycloak: KeycloakCoreMock): void {
  mockKeycloak.authenticated = false;
  mockKeycloak.token = null;
  mockKeycloak.tokenParsed = null;
  mockKeycloak.onAuthSuccess = undefined;
  mockKeycloak.onAuthLogout = undefined;
  mockKeycloak.onAuthRefreshSuccess = undefined;
  mockKeycloak.onAuthRefreshError = undefined;
}
