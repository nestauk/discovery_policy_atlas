import { Inter } from 'next/font/google'
import './globals.css'
import 'antd/dist/reset.css'
import { ProviderRoot } from '@/components/auth/providers';
import { ConditionalHeader } from '@/components/LayoutWrapper';

const inter = Inter({ subsets: ['latin'] })

export const metadata = {
  title: 'Policy Atlas',
  description: 'AI-powered policy research tool',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <base target="_blank" />
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
      </head>
      <body className={inter.className}>
        <ProviderRoot>
          <ConditionalHeader />
          {children}
        </ProviderRoot>
      </body>
    </html>
  )
}