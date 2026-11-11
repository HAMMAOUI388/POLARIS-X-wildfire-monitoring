"use client";

import { FormEvent, useEffect, useState } from "react";
import { Compass, LoaderCircle, Lock, LogOut, ShieldCheck } from "lucide-react";
import { evaluateRoles, PolarisApi, User } from "@/lib/api";
import { PublicPortal } from "@/components/public-portal";
import { ProfessionalPortal } from "@/components/professional-portal";

export function Dashboard() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authForm, setAuthForm] = useState({ email: "", password: "", display_name: "" });

  const [api] = useState(
    () =>
      new PolarisApi(undefined, {
        onUnauthorized: () => {
          if (typeof window !== "undefined") {
            sessionStorage.removeItem("polaris_access");
            sessionStorage.removeItem("polaris_refresh");
          }
          setUser(null);
        },
        onTokensUpdated: token => {
          if (typeof window !== "undefined") sessionStorage.setItem("polaris_access", token);
        },
      })
  );

  // Portal view state for dual-role users (e.g. admin inspecting public view)
  const [portalView, setPortalView] = useState<"professional" | "public">("public");

  useEffect(() => {
    const access = sessionStorage.getItem("polaris_access");
    const refresh = sessionStorage.getItem("polaris_refresh");
    if (!access) {
      setReady(true);
      return;
    }
    api.setTokens(access, refresh);
    api
      .me()
      .then(result => {
        setUser(result.user);
        const roles = evaluateRoles(result.user.roles);
        if (roles.portal === "professional") {
          setPortalView("professional");
        } else {
          setPortalView("public");
        }
      })
      .catch(() => {
        sessionStorage.removeItem("polaris_access");
        sessionStorage.removeItem("polaris_refresh");
        api.setTokens(null, null);
      })
      .finally(() => setReady(true));
  }, [api]);

  const doLogout = () => {
    sessionStorage.removeItem("polaris_access");
    sessionStorage.removeItem("polaris_refresh");
    api.setTokens(null, null);
    setUser(null);
  };

  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (authMode === "register") {
        await api.register(authForm.email, authForm.password, authForm.display_name);
      }
      const result = await api.login(authForm.email, authForm.password);
      api.setTokens(result.access_token, result.refresh_token);
      sessionStorage.setItem("polaris_access", result.access_token);
      sessionStorage.setItem("polaris_refresh", result.refresh_token);
      setUser(result.user);

      const roles = evaluateRoles(result.user.roles);
      if (roles.portal === "professional") {
        setPortalView("professional");
      } else {
        setPortalView("public");
      }
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-[#60736b]">
        <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
        Connecting to your workspace…
      </div>
    );
  }

  // 1. Unauthenticated State
  if (!user) {
    return (
      <main className="grid min-h-screen bg-[#f7f8f4] lg:grid-cols-[1.05fr_.95fr]">
        <section className="relative hidden overflow-hidden bg-[#123c35] p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div className="absolute -right-28 -top-28 h-[420px] w-[420px] rounded-full border border-white/10" />
          <div className="absolute -right-8 -top-8 h-[280px] w-[280px] rounded-full border border-white/10" />
          <div className="relative flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-2xl bg-white/10">
              <Compass className="h-6 w-6 text-[#93d2a9]" />
            </div>
            <div>
              <div className="text-lg font-bold tracking-[.16em]">POLARIS X</div>
              <div className="text-xs text-white/55">WILDFIRE MONITORING</div>
            </div>
          </div>
          <div className="relative max-w-xl">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-[#c7e5d2]">
              <span className="h-2 w-2 rounded-full bg-[#83c998]" /> Satellite intelligence workspace
            </div>
            <h1 className="text-5xl font-semibold leading-[1.08] tracking-[-.04em]">
              See the signal.
              <br />
              <span className="text-[#a9d9b8]">Understand the context.</span>
            </h1>
            <p className="mt-6 max-w-md text-[15px] leading-7 text-white/65">
              A clear operational view of satellite thermal anomalies, saved places and weather context across your monitored areas.
            </p>
            <div className="mt-10 flex items-center gap-3 text-xs text-white/55">
              <ShieldCheck className="h-4 w-4 text-[#93d2a9]" /> Private to your account and shared monitoring locations
            </div>
          </div>
          <div className="relative flex items-end justify-between text-xs text-white/45">
            <span>Morocco monitoring prototype</span>
            <span>Data has limitations · anomalies are not confirmations</span>
          </div>
        </section>

        <section className="flex items-center justify-center px-6 py-14">
          <div className="w-full max-w-[420px]">
            <div className="mb-8 flex items-center gap-3 lg:hidden">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#176b58]">
                <Compass className="h-6 w-6 text-white" />
              </div>
              <div className="font-bold tracking-[.16em]">POLARIS X</div>
            </div>
            <div className="mb-8">
              <div className="text-sm font-medium text-[#176b58]">MONITORING CONSOLE</div>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">
                {authMode === "login" ? "Welcome back" : "Create your account"}
              </h2>
              <p className="mt-2 text-sm text-[#73817a]">
                {authMode === "login"
                  ? "Sign in to view your monitoring workspace."
                  : "Set up a private account for your saved locations."}
              </p>
            </div>
            {error && (
              <div role="alert" className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <form className="space-y-4" onSubmit={authenticate}>
              {authMode === "register" && (
                <label className="block text-sm font-medium">
                  Display name
                  <input
                    required
                    value={authForm.display_name}
                    onChange={e => setAuthForm({ ...authForm, display_name: e.target.value })}
                    className="mt-1.5 w-full rounded-xl border border-[#dde5de] bg-white px-3.5 py-3 outline-none focus:border-[#176b58]"
                    autoComplete="name"
                  />
                </label>
              )}
              <label className="block text-sm font-medium">
                Email address
                <input
                  type="email"
                  required
                  value={authForm.email}
                  onChange={e => setAuthForm({ ...authForm, email: e.target.value })}
                  className="mt-1.5 w-full rounded-xl border border-[#dde5de] bg-white px-3.5 py-3 outline-none focus:border-[#176b58]"
                  autoComplete="email"
                />
              </label>
              <label className="block text-sm font-medium">
                Password
                <input
                  type="password"
                  required
                  minLength={authMode === "register" ? 12 : 1}
                  value={authForm.password}
                  onChange={e => setAuthForm({ ...authForm, password: e.target.value })}
                  className="mt-1.5 w-full rounded-xl border border-[#dde5de] bg-white px-3.5 py-3 outline-none focus:border-[#176b58]"
                  autoComplete={authMode === "login" ? "current-password" : "new-password"}
                />
              </label>
              <button
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#176b58] py-3.5 font-medium text-white transition hover:bg-[#125646] disabled:opacity-60"
              >
                {busy && <LoaderCircle className="h-4 w-4 animate-spin" />}
                {authMode === "login" ? "Sign in" : "Create account"}
              </button>
            </form>
            <p className="mt-5 text-center text-sm text-[#73817a]">
              {authMode === "login" ? "New to POLARIS X?" : "Already have an account?"}{" "}
              <button
                onClick={() => {
                  setError("");
                  setAuthMode(authMode === "login" ? "register" : "login");
                }}
                className="font-semibold text-[#176b58]"
              >
                {authMode === "login" ? "Create account" : "Sign in"}
              </button>
            </p>
            <div className="mt-8 rounded-xl bg-[#eef3ed] p-4 text-xs leading-5 text-[#62736b]">
              The dashboard reports satellite thermal anomalies and associated data. It does not provide confirmed wildfire diagnoses or validated fire predictions.
            </div>
          </div>
        </section>
      </main>
    );
  }

  // 2. Strict Role Evaluation
  const roleEvaluation = evaluateRoles(user.roles);

  // 3. Access Denied State (Missing, empty, or unknown roles)
  if (roleEvaluation.portal === "denied") {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#f7f8f4] p-6 text-center">
        <div className="w-full max-w-md rounded-[22px] border border-[#f2d7ce] bg-white p-8 shadow-card">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-[#fff0e9] text-[#de5732]">
            <Lock className="h-7 w-7" />
          </div>
          <h2 className="mt-4 text-xl font-bold text-[#2a1a15]">Access Denied: Unrecognized Role</h2>
          <p className="mt-2 text-xs leading-5 text-[#73635d]">
            Your authenticated account ({user.email}) has no recognized platform role.
            Expected roles: <code className="bg-[#f0f4ef] px-1 py-0.5 rounded text-[#224e3c]">user</code>,{" "}
            <code className="bg-[#f0f4ef] px-1 py-0.5 rounded text-[#224e3c]">farm_owner</code>,{" "}
            <code className="bg-[#f0f4ef] px-1 py-0.5 rounded text-[#224e3c]">authority</code>, or{" "}
            <code className="bg-[#f0f4ef] px-1 py-0.5 rounded text-[#224e3c]">admin</code>.
          </p>
          <div className="mt-4 rounded-xl bg-[#f8faf8] border border-[#e8ece5] p-3 text-xs text-[#52645a]">
            Reported Roles: {user.roles?.length ? user.roles.join(", ") : "None"}
          </div>
          <button
            onClick={doLogout}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-[#176b58] py-3 text-xs font-semibold text-white hover:bg-[#125646]"
          >
            <LogOut className="h-4 w-4" /> Sign Out
          </button>
        </div>
      </main>
    );
  }

  // 4. Professional Portal Routing
  if (roleEvaluation.portal === "professional") {
    // Only admin can switch to public view; authority is strictly locked to professional
    if (roleEvaluation.isAdmin && portalView === "public") {
      return (
        <PublicPortal
          api={api}
          user={user}
          canSwitchToProfessional={true}
          onSwitchPortal={setPortalView}
          onLogout={doLogout}
        />
      );
    }

    return (
      <ProfessionalPortal
        api={api}
        user={user}
        isAdmin={roleEvaluation.isAdmin}
        canSwitchToPublic={roleEvaluation.canSwitchToPublic}
        onSwitchPortal={setPortalView}
        onLogout={doLogout}
      />
    );
  }

  // 5. Public Portal Routing (roles 'user' or 'farm_owner')
  return (
    <PublicPortal
      api={api}
      user={user}
      canSwitchToProfessional={false}
      onLogout={doLogout}
    />
  );
}
