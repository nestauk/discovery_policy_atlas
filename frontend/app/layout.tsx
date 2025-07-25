// import { Inter } from 'next/font/google'
import './globals.css'
import 'antd/dist/reset.css'
import { LayoutWrapper } from '@/components/layout-wrapper';

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
      </head>
      <LayoutWrapper>
        {children}
      </LayoutWrapper>
    </html>
  )
}