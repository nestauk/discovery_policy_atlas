'use client'

import Link from "next/link";
import { SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] px-4 text-center">
      <h1 className="text-5xl font-bold mb-4">🌐 Policy Atlas</h1>
      <p className="text-xl text-gray-600 mb-8">
        Harnessing AI to improve policy design
      </p>
      <div className="space-x-4">
        <SignInButton mode="modal">
          <Button className="px-6 py-3 text-lg">Sign In</Button>
        </SignInButton>
        <Link href="https://www.nesta.org.uk/project/policy-atlas-harnessing-ai-to-improve-policy-design/" passHref>
          <Button variant="outline" className="px-6 py-3 text-lg">Read More</Button>
        </Link>
      </div>
    </div>
  );
}