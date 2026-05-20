/**
 * Resolves the active auth provider from the env at module load.
 *
 * The selector lives in exactly one place; every consumer (React provider,
 * middleware, components) reads from here so we can swap implementations
 * by flipping `NEXT_PUBLIC_AUTH_PROVIDER`.
 */

export type AuthProviderName = 'clerk' | 'cognito'

const RAW = process.env.NEXT_PUBLIC_AUTH_PROVIDER?.toLowerCase()

export const AUTH_PROVIDER: AuthProviderName =
  RAW === 'cognito' ? 'cognito' : 'clerk'
