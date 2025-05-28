import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Change from: export function middleware
// To: export function middleware (or use default export)
export function middleware(request: NextRequest) {
  // Simple pass-through for now
  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}