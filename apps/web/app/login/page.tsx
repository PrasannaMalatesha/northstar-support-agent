import { LoginForm } from "@/app/login-form";
import { loginAction } from "@/app/login-action";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const params = await searchParams;
  const error =
    params.error === "locked"
      ? "This login is locked. Try again later."
      : params.error
        ? "Email or password is incorrect."
        : undefined;

  return (
    <main className="screen">
      <h1>Northstar</h1>
      <p className="lede">Sign in to the case desk.</p>
      <LoginForm action={loginAction} error={error} />
    </main>
  );
}
