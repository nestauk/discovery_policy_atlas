// frontend/auth.ts
import NextAuth from "next-auth"
import Credentials from "next-auth/providers/credentials"

const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" }
      },
      authorize: async (credentials) => {
        // Simple check for demo
        if (credentials?.email === "test@example.com" && credentials?.password === "password123") {
          return {
            id: "1",
            email: "test@example.com",
            name: "Test User",
          }
        }
        return null
      }
    })
  ],
  pages: {
    signIn: "/login",
  }
})

export { handlers, signIn, signOut, auth }