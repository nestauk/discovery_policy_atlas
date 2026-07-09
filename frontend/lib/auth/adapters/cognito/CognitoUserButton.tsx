'use client'

import { LogOut, User as UserIcon } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuth } from '../../context'

/**
 * Minimal user popover for Cognito.
 *
 * Mirrors the visual role of Clerk's `<UserButton>`: a circular avatar that
 * opens a dropdown with the user's identity and a sign-out action. Styled
 * via the existing radix-based dropdown primitives so it inherits the
 * site's look-and-feel.
 */
export function CognitoUserButton() {
  const { user, signOut } = useAuth()

  if (!user) return null

  const initial = (user.firstName || user.name || user.email || '?').charAt(0).toUpperCase()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Open user menu"
        className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
      >
        {initial}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[12rem]">
        <DropdownMenuLabel className="flex items-center gap-2">
          <UserIcon className="h-4 w-4 text-slate-500" />
          <div className="flex flex-col">
            <span className="font-medium text-slate-900 leading-tight">
              {user.name || user.email || 'User'}
            </span>
            {user.email && user.email !== user.name && (
              <span className="text-xs text-slate-500 leading-tight">{user.email}</span>
            )}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          variant="destructive"
          onClick={() => {
            void signOut()
          }}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
