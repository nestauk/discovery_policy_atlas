'use client'

import { usePathname } from "next/navigation";
import { Header } from "@/components/header";

export function ConditionalHeader() {
  const pathname = usePathname();
  const isLoginPage = pathname === '/login';
  const isAgentPage = pathname?.startsWith('/agent');
  const isV2Page = pathname?.startsWith('/v2');

  if (isLoginPage || isAgentPage || isV2Page) {
    return null;
  }

  return <Header />;
} 