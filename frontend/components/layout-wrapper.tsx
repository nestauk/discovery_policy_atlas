'use client'

import { usePathname } from "next/navigation";
import { Header } from "@/components/header";

export function ConditionalHeader() {
  const pathname = usePathname();
  const isLoginPage = pathname === '/login';
  const isHomePage = pathname === '/';
  
  // Routes that use the (main) layout with sidebar - don't show header
  const mainAppRoutes = ['/projects', '/search', '/results', '/faq', '/test_extraction', '/text_extractions'];
  const isMainAppPage = mainAppRoutes.some(route => pathname?.startsWith(route));

  if (isLoginPage || isHomePage || isMainAppPage) {
    return null;
  }

  return <Header />;
} 