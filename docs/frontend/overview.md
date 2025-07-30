# Frontend overview

The Policy Atlas frontend is built with **Next.js 15** and **React 19**, following component-driven architecture with TypeScript for type safety.

## Core principles
**Component-driven design**: Reusable, modular components<br>
**Type-safe development**: Comprehensive TypeScript usage<br>

### Tech stack
- **Next.js 15** with App Router
- **React 19** with modern hooks and features
- **TypeScript** for type safety
- **Tailwind CSS** for styling
- **Clerk** for authentication
- **shadcn/ui + Ant Design** for UI components

## Structure

```
frontend/
├── app/                            # Next.js App Router
│   ├── dashboard/                  # Main application pages
│   │   ├── home/
│   │   │   └── page.tsx           # Dashboard home page
│   │   ├── search/
│   │   │   └── page.tsx           # Search interface
│   │   ├── simulation/
│   │   │   └── page.tsx           # Policy simulation (planned)
│   │   ├── synthesis/
│   │   │   └── page.tsx           # Research synthesis
│   │   ├── layout.tsx             # Dashboard layout wrapper
│   │   └── page.tsx               # Dashboard root
│   │
│   ├── login/                     # Authentication pages
│   │   ├── layout.tsx             # Login layout
│   │   └── page.tsx               # Login form
│   │
│   ├── layout.tsx                 # Root application layout
│   ├── page.tsx                   # Landing page
│   └── globals.css                # Global styles
│
├── components/                    # Reusable React components
│   ├── auth/                      # Authentication components
│   │   ├── auth-buttons.tsx       # Login/logout buttons
│   │   └── login-form.tsx         # Login form component
│   │
│   ├── search/                    # Search-related components
│   │   ├── ai-summary.tsx         # AI-generated summaries
│   │   ├── download-button.tsx    # Export functionality
│   │   ├── error-message.tsx      # Error display
│   │   ├── paper-card.tsx         # Individual paper card
│   │   ├── papers-list.tsx        # Paper list view
│   │   ├── papers-table.tsx       # Paper table view
│   │   ├── search-form.tsx        # Search input form
│   │   ├── search-results.tsx     # Results container
│   │   ├── search-summary.tsx     # Search metadata
│   │   └── view-toggle.tsx        # List/table view toggle
│   │
│   ├── ui/                        # Base UI components (shadcn/ui)
│   │   ├── avatar.tsx             # User avatar
│   │   ├── badge.tsx              # Status badges
│   │   ├── button.tsx             # Button variants
│   │   ├── card.tsx               # Card container
│   │   └── ...                    # Additional UI primitives
│   │
│   ├── header.tsx                 # Application header
│   └── layout-wrapper.tsx         # Main layout wrapper
│
├── lib/                           # Utility libraries
│   ├── api.ts                     # Backend API client
│   ├── constants.ts               # Application constants
│   ├── searchStore.ts             # Zustand search state
│   ├── utils.ts                   # Utility functions
│   └── hash-passwords.ts          # Password utilities (not sure if needed anymore)
│
├── types/                         # TypeScript definitions
│   └── search.ts                  # Search-related types
│
├── Styling
│   ├── tailwind.config.ts         # Tailwind CSS config
│   ├── components.json            # shadcn/ui config
│   ├── postcss.config.mjs         # PostCSS config
│
└── 📦 Configuration files
    ├── package.json               # Dependencies and scripts
    ├── tsconfig.json              # TypeScript config
    ├── next.config.ts             # Next.js config
    ├── middleware.ts              # Next.js middleware
    └── eslint.config.mjs          # ESLint configuration    
```

## Authentication

The application uses **Clerk** for comprehensive authentication management. Authentication is handled at the layout level with conditional rendering based on the current route.

```typescript
// components/layout-wrapper.tsx
import { ClerkProvider } from "@clerk/nextjs";

export function LayoutWrapper({ children }) {
  return (
    <ClerkProvider>
      <body className={inter.className}>
        {!isLoginPage && <Header />}
        {children}
      </body>
    </ClerkProvider>
  );
}
```
