import { signIn, ssoOn } from "@/auth";
import { LoginForm } from "@/app/login-form";
import { loginAction } from "@/app/login-action";

async function googleAction() {
  "use server";
  await signIn("google", { redirectTo: "/desk" });
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; expired?: string }>;
}) {
  const params = await searchParams;
  const error =
    params.expired !== undefined && !params.error
      ? "Your session ended. Sign in again."
      : params.error === "locked"
      ? "This login is locked. Try again later."
      : params.error === "sso"
        ? "This Google account cannot sign in here."
        : params.error
          ? "Email or password is incorrect."
          : undefined;

  return (
    <main className="screen">
      <h1>Northstar</h1>
      <p className="lede">Sign in to the case desk.</p>
      {ssoOn ? (
        <form action={googleAction}>
          {error ? <p role="alert">{error}</p> : null}
          <button type="submit">Sign in with Google</button>
        </form>
      ) : (
        <LoginForm action={loginAction} error={error} />
      )}
    </main>
  );
}
