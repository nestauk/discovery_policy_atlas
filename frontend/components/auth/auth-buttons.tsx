'use client'

import {
  SignInButton,
  SignUpButton,
  SignedIn,
  SignedOut,
  UserButton,
} from "@clerk/nextjs";
import { Button } from "@/components/ui/button";

export function AuthButtons() {
  return (
    <>
      <SignedOut>
        <div className="space-x-4">
          <SignInButton mode="modal">
            <Button variant="ghost">Sign In</Button>
          </SignInButton>
          <SignUpButton mode="modal">
            <Button>Sign Up</Button>
          </SignUpButton>
        </div>
      </SignedOut>
      <SignedIn>
        <UserButton />
      </SignedIn>
    </>
  );
} 