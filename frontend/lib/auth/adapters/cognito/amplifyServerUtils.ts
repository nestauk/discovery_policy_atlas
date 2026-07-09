/**
 * Amplify server runner for the Cognito httpOnly auth flow.
 *
 * `createServerRunner` builds the helpers used by the server-side auth flow:
 *  - `runWithAmplifyServerContext` runs server-only Amplify APIs (e.g.
 *    `fetchAuthSession`) in an isolated per-request context, reading/writing
 *    the httpOnly token cookies.
 *  - `createAuthRouteHandlers` generates the `/api/auth/*` Route Handlers that
 *    drive the Managed Login sign-in/out + token-exchange flow.
 *
 * Cookie attributes: `secure` is set automatically based on whether
 * `AMPLIFY_APP_ORIGIN` is https. `sameSite=lax` lets the cookies ride the
 * top-level redirect back from Cognito's Managed Login.
 */

import { createServerRunner } from '@aws-amplify/adapter-nextjs'

import { buildCognitoResourceConfig } from './config'

const REFRESH_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 30 // 30 days

export const { runWithAmplifyServerContext, createAuthRouteHandlers } =
  createServerRunner({
    config: buildCognitoResourceConfig(),
    runtimeOptions: {
      cookies: {
        sameSite: 'lax',
        maxAge: REFRESH_TOKEN_MAX_AGE_SECONDS,
      },
    },
  })
