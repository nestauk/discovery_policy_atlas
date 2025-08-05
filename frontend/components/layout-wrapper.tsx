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

  return (
    <ClerkProvider>
      <body className={inter.className}>
        {!isLoginPage && !isAgentPage && <Header />}
        {children}
      </body>
    </ClerkProvider>
  );
} 