/**
 * Token access for code that runs outside the React tree.
 *
 * Zustand stores and other non-React modules can't use `useAuth`, but they
 * still need a bearer token. The active adapter calls
 * `registerExternalTokenGetter` from a `useEffect` on mount, and non-React
 * callers use `getExternalToken`. This keeps the rest of the codebase free
 * of direct `window.Clerk` (or future `Auth.fetchAuthSession`) references.
 */

type TokenGetter = () => Promise<string | null>

let getterRef: TokenGetter | null = null

export function registerExternalTokenGetter(getter: TokenGetter): () => void {
  getterRef = getter
  return () => {
    if (getterRef === getter) {
      getterRef = null
    }
  }
}

export async function getExternalToken(): Promise<string | null> {
  if (!getterRef) return null
  try {
    return await getterRef()
  } catch {
    return null
  }
}
