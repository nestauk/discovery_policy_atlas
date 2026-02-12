import Link from "next/link";
import { AuthButtons } from "@/components/auth/AuthButtons";

export function Header() {
  return (
    <header className="border-b bg-white px-8 py-4">
      <div className="max-w-6xl mx-auto flex justify-between items-center">
        <Link href="/">
          <h1 className="text-xl font-semibold cursor-pointer">🌐 Policy Atlas</h1>
        </Link>
        <AuthButtons />
      </div>
    </header>
  );
}