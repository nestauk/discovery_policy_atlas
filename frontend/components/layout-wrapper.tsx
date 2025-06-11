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

  return (
    <ClerkProvider>
      <body className={inter.className}>
        {!isLoginPage && <Header />}
        {children}
      </body>
    </ClerkProvider>
  );
} 