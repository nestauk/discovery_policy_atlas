import { AuthButtons } from "@/components/auth/auth-buttons";

export function Header() {
  return (
    <header className="flex justify-between items-center p-4 border-b">
      <h1 className="text-xl font-semibold">🌐 Policy Atlas</h1>
      <AuthButtons />
    </header>
  );
} 