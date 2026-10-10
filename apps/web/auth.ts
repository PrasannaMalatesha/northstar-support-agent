import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { endsSoon, renew } from "@/staff-session";

const apiUrl = process.env.FASTAPI_URL ?? "http://127.0.0.1:8000";

// Google single sign-on is on when AUTH_GOOGLE_ID is set (issue #78). Then no password form is offered.
export const ssoOn = Boolean(process.env.AUTH_GOOGLE_ID);

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt", maxAge: 15 * 60 },
  pages: { signIn: "/login" },
  providers: ssoOn
    ? [Google]
    : [
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
    // The API checks Google's ID token and returns staff tokens; the role comes from the staff record.
    // Without an adapter, Auth.js hands this same user object to jwt() below.
    async signIn({ user, account }) {
      if (account?.provider !== "google") {
        return true;
      }
      const response = await fetch(`${apiUrl}/auth/sso`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: account.id_token ?? "" }),
      });
      if (!response.ok) {
        return "/login?error=sso";
      }
      const body = (await response.json()) as {
        access_token: string;
        refresh_token: string;
        name: string;
        role: string;
      };
      Object.assign(user, {
        name: body.name,
        role: body.role,
        accessToken: body.access_token,
        refreshToken: body.refresh_token,
      });
      return true;
    },
    // The API token lasts 15 minutes. Shortly before it ends it is renewed, so a working specialist stays
    // signed in. A refused renewal ends the session, and the sign-in page shows.
    async jwt({ token, user }) {
      if (user) {
        token.role = user.role;
        token.accessToken = user.accessToken;
        token.refreshToken = user.refreshToken;
        return token;
      }
      if (typeof token.accessToken === "string" && endsSoon(token.accessToken)) {
        const renewed = typeof token.refreshToken === "string" ? await renew(token.refreshToken) : null;
        if (!renewed) {
          return null;
        }
        token.accessToken = renewed.accessToken;
        token.refreshToken = renewed.refreshToken;
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
