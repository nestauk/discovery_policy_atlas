'use client'

import { SignIn } from "@clerk/nextjs"

export function LoginForm() {
  return (
    <div className="flex justify-center items-center min-h-[400px]">
      <SignIn />
    </div>
  )
}