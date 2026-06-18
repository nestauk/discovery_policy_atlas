/**
 * Public surface of the in-house auth wrapper.
 *
 * The rest of the app imports from here. Adapters and their dependencies
 * (Clerk SDK, Amplify, etc.) stay behind this barrel.
 */

export { AuthProvider } from './AuthProvider'
export { useAuth } from './context'
export { getExternalToken } from './external'
export { SignInButton } from './components/SignInButton'
export { UserButton } from './components/UserButton'
export { SignedIn } from './components/SignedIn'
export { SignedOut } from './components/SignedOut'
export type {
  AuthContextValue,
  AuthUser,
  AuthOrganization,
  AuthMembership,
} from './types'
export { AUTH_PROVIDER } from './config'
export type { AuthProviderName } from './config'
