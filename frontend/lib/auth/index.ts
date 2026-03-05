/**
 * Provider-agnostic auth exports.
 * Use these throughout the app instead of importing directly from Clerk/BetterAuth.
 */

export * from './types';
export * from './provider';

// Token acquisition
export { useAuthToken, getTokenExternal } from './token';

// User and organization hooks
export { useAuthUser, useAuthOrganization, useUser, useOrganization } from './hooks';
