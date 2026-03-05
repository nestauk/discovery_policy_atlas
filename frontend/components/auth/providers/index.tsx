'use client';

/**
 * Provider-agnostic auth UI component exports.
 * Routes to the correct provider based on NEXT_PUBLIC_AUTH_PROVIDER.
 * 
 * The provider is determined at module load time. The environment variable
 * NEXT_PUBLIC_AUTH_PROVIDER must be set to 'clerk' or 'keycloak'.
 *
 * Usage:
 *   import { AuthButtons, LoginForm, OrganizationManager, ProviderRoot } from '@/components/auth/providers';
 */

import { isClerkProvider } from '@/lib/auth/provider';

// Import all provider components statically
// The bundler will tree-shake unused code in production
import {
  AuthButtons as ClerkAuthButtons,
  LoginForm as ClerkLoginForm,
  OrganizationManager as ClerkOrganizationManager,
  ProviderRoot as ClerkProviderRoot,
  SignInButton as ClerkSignInButton,
  SignUpButton as ClerkSignUpButton,
  SignedIn as ClerkSignedIn,
  SignedOut as ClerkSignedOut,
  UserButton as ClerkUserButton,
  SignIn as ClerkSignIn,
} from './clerk';

import {
  AuthButtons as KeycloakAuthButtons,
  LoginForm as KeycloakLoginForm,
  OrganizationManager as KeycloakOrganizationManager,
  ProviderRoot as KeycloakProviderRoot,
  SignInButton as KeycloakSignInButton,
  SignUpButton as KeycloakSignUpButton,
  SignedIn as KeycloakSignedIn,
  SignedOut as KeycloakSignedOut,
  UserButton as KeycloakUserButton,
  SignInPage as KeycloakSignIn,
} from './keycloak';

// Select component implementations based on provider
const isClerk = isClerkProvider();

// Re-export based on provider
export const ProviderRoot = isClerk ? ClerkProviderRoot : KeycloakProviderRoot;
export const AuthButtons = isClerk ? ClerkAuthButtons : KeycloakAuthButtons;
export const LoginForm = isClerk ? ClerkLoginForm : KeycloakLoginForm;
export const OrganizationManager = isClerk ? ClerkOrganizationManager : KeycloakOrganizationManager;
export const SignInButton = isClerk ? ClerkSignInButton : KeycloakSignInButton;
export const SignUpButton = isClerk ? ClerkSignUpButton : KeycloakSignUpButton;
export const UserButton = isClerk ? ClerkUserButton : KeycloakUserButton;
export const SignedIn = isClerk ? ClerkSignedIn : KeycloakSignedIn;
export const SignedOut = isClerk ? ClerkSignedOut : KeycloakSignedOut;
export const SignIn = isClerk ? ClerkSignIn : KeycloakSignIn;

// Export provider name helper
export { getAuthProviderName } from '@/lib/auth/provider';
