import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt", maxAge: 15 * 60 },
  pages: { signIn: "/login" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email" },
        password: { label: "Password", type: "password" },
      },
      authorize: async (credentials) => {
        const email = String(credentials?.email ?? "");
        const password = String(credentials?.password ?? "");
        const response = await fetch(`${apiUrl}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!response.ok) {
          return null;
        }
        const body = (await response.json()) as {
          access_token: string;
          refresh_token: string;
          name: string;
          role: string;
        };
        return {
          id: email,
          name: body.name,
          email,
          role: body.role,
          accessToken: body.access_token,
          refreshToken: body.refresh_token,
        };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.role = user.role;
        token.accessToken = user.accessToken;
        token.refreshToken = user.refreshToken;
      }
      return token;
    },
    session({ session, token }) {
      return {
        ...session,
        user: {
          name: session.user?.name ?? null,
          role: token.role ?? "",
        } as typeof session.user,
      };
    },
  },
});
