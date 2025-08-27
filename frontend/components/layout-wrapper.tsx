'use client'

import { ClerkProvider } from "@clerk/nextjs"; 
import { usePathname } from "next/navigation";
import { Header } from "@/components/header";
import { Inter } from 'next/font/google'

const inter = Inter({ subsets: ['latin'] })

export function LayoutWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const isLoginPage = pathname === '/login';
  const isAgentPage = pathname?.startsWith('/agent');
  const isV2Page = pathname?.startsWith('/v2');

  return (
    <ClerkProvider>
      <body className={inter.className}>
        {!isLoginPage && !isAgentPage && !isV2Page && <Header />}
        {children}
      </body>
    </ClerkProvider>
  );
} 