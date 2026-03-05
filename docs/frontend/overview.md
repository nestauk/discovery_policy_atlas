# Frontend overview

The Policy Atlas frontend is built with **Next.js 16** and **React 19**, following component-driven architecture with TypeScript for type safety.

## Core principles
**Component-driven design**: Reusable, modular components<br>
**Type-safe development**: Comprehensive TypeScript usage<br>

### Tech stack
- **Next.js 16** with App Router
- **React 19** with modern hooks and features
- **TypeScript** for type safety
- **Tailwind CSS** for styling
- **Clerk** and **Keycloak** via a provider-agnostic auth layer
- **shadcn/ui + Ant Design** for UI components

## Structure

```
frontend/
├── app/                               # Next.js App Router
│   ├── (main)/                        # Authenticated app routes
│   │   ├── layout.tsx
│   │   ├── page.tsx                    # Landing page
│   │   ├── projects/
│   │   ├── results/
│   │   ├── search/
│   │   └── faq/
│   ├── login/                          # Authentication pages
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── layout.tsx                      # Root application layout
│   └── globals.css                     # Global styles
│
├── components/                         # Reusable React components
│   ├── auth/                           # Authentication UI
│   │   ├── AuthButtons.tsx
│   │   ├── LoginForm.tsx
│   │   └── providers/                  # Provider-specific UI
│   │       ├── clerk/
│   │       └── keycloak/
│   ├── chatbot/                        # Chat interface components
│   ├── interventions/                  # Intervention workflows
│   ├── landing/                        # Landing page sections
│   ├── results/                        # Results display
│   ├── search/                         # Search UI
│   └── ui/                             # Base UI primitives (shadcn/ui)
│
├── lib/                                # Client utilities and stores
│   ├── api.ts
│   ├── auth/                           # Provider-agnostic auth utilities
│   │   ├── provider.ts
│   │   └── providers/                  # Provider-specific logic
│   ├── analysisProjectStore.ts
│   ├── chatStore.ts
│   ├── evidenceCategories.ts
│   └── utils.ts
│
├── public/                             # Public assets
├── types/                              # TypeScript definitions
├── tailwind.config.ts                  # Tailwind CSS config
├── postcss.config.mjs                  # PostCSS config
└── package.json                        # Dependencies and scripts
```

## Authentication

Authentication is provider-agnostic. The app selects **Clerk** or **Keycloak** via `NEXT_PUBLIC_AUTH_PROVIDER`, and routes UI + hooks through a shared interface in `lib/auth` and `components/auth/providers`.
