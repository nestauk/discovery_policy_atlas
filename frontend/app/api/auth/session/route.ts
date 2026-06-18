/**
 * Session/token endpoint for the Cognito httpOnly flow.
 *
 * The access + refresh tokens live in httpOnly cookies on the Next.js origin,
 * so client JS can't read them directly. The separate FastAPI backend
 * (different origin) still authenticates with a bearer access token, so this
 * route reads the session server-side and hands the client the short-lived
 * access token (held in memory) plus the user's identity claims.
 *
 * Uses `{ request, response }` server context (not `cookies()` alone) so Amplify
 * reads the same httpOnly auth cookies set by the sign-in-callback handler.
 *
 * The refresh token is never returned — it stays httpOnly. This is the
 * "Option B" posture: refresh token httpOnly, access token in memory.
 */

import { fetchAuthSession } from 'aws-amplify/auth/server'
import { NextRequest, NextResponse } from 'next/server'

import { runWithAmplifyServerContext } from '@/lib/auth/adapters/cognito/amplifyServerUtils'

export const dynamic = 'force-dynamic'

function asString(value: unknown): string | undefined {
  return typeof value === 'string' && value ? value : undefined
}

function withRefreshedCookies(
  source: NextResponse,
  target: NextResponse
): NextResponse {
  for (const cookie of source.cookies.getAll()) {
    target.cookies.set(cookie)
  }
  return target
}

export async function GET(request: NextRequest) {
  const amplifyResponse = NextResponse.next()

  try {
    const data = await runWithAmplifyServerContext({
      nextServerContext: { request, response: amplifyResponse },
      operation: async (contextSpec) => {
        const session = await fetchAuthSession(contextSpec)
        const accessToken = session.tokens?.accessToken
        if (!accessToken) return null

        const idPayload = session.tokens?.idToken?.payload
        const accessPayload = accessToken.payload
        const exp = accessPayload?.exp

        return {
          accessToken: accessToken.toString(),
          expiresAt: typeof exp === 'number' ? exp * 1000 : null,
          user: {
            id: asString(idPayload?.sub) ?? asString(accessPayload?.sub) ?? '',
            email: asString(idPayload?.email),
            name:
              asString(idPayload?.name) ??
              asString(idPayload?.given_name) ??
              asString(idPayload?.['cognito:username']),
            firstName: asString(idPayload?.given_name),
          },
        }
      },
    })

    if (!data) {
      return NextResponse.json({ authenticated: false }, { status: 401 })
    }

    return withRefreshedCookies(
      amplifyResponse,
      NextResponse.json({ authenticated: true, ...data })
    )
  } catch {
    return NextResponse.json({ authenticated: false }, { status: 401 })
  }
}
