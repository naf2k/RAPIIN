import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  LoaderCircle,
  ShieldCheck,
} from "lucide-react";

import { RapiinLogo } from "@/components/ui/rapiin-logo";
import { ApiError, apiGet, apiPost } from "@/lib/api";
import { setSession } from "@/lib/session";
import type { Device, LoginResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

type LoginStatus = "idle" | "loading" | "success";

const moonImage = "/moon.png";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [status, setStatus] = useState<LoginStatus>("idle");
  const [error, setError] = useState("");
  const timersRef = useRef<number[]>([]);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Login | RAPIIN";
    return () => {
      document.title = previousTitle;
      timersRef.current.forEach((timer) => window.clearTimeout(timer));
    };
  }, []);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (status !== "idle") return;

    const normalizedEmail = email.trim();
    if (!/^\S+@\S+\.\S+$/.test(normalizedEmail)) {
      setError("Masukkan email organisasi yang valid.");
      return;
    }
    if (password.length < 8) {
      setError("Kata sandi minimal 8 karakter.");
      return;
    }

    setError("");
    setStatus("loading");

    apiPost<LoginResponse>("/auth/login", { email: normalizedEmail, password })
      .then(async (data) => {
        setSession(data.token, {
          user_id: data.user_id,
          name: data.name,
          role: data.role,
        });
        setStatus("success");

        // The login payload omits the email; /auth/me has the full identity.
        try {
          const me = await apiGet<{ email: string }>("/auth/me");
          setSession(data.token, {
            user_id: data.user_id,
            name: data.name,
            role: data.role,
            email: me.email,
          });
        } catch {
          // Email is only used for display.
        }

        let target = data.role === "SUPERVISOR" ? "/supervisor" : "/";
        if (data.role === "USER") {
          try {
            const devices = await apiGet<Device[]>("/user/devices");
            // An account created by a supervisor has no device paired yet.
            if (devices.length === 0) target = "/onboarding";
          } catch {
            // Fall through to the chat; Settings still shows device state.
          }
        }

        const redirectTimer = window.setTimeout(() => {
          window.location.assign(target);
        }, reducedMotion ? 0 : 480);
        timersRef.current.push(redirectTimer);
      })
      .catch((cause: unknown) => {
        setStatus("idle");
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Terjadi kesalahan. Silakan coba lagi.",
        );
      });
  };

  const isSubmitting = status !== "idle";

  return (
    <main className="dark grid min-h-[100dvh] overflow-hidden bg-[#050505] text-neutral-100 lg:grid-cols-[minmax(0,1.12fr)_minmax(460px,0.88fr)]">
      <section className="relative hidden min-h-[100dvh] overflow-hidden border-r border-neutral-800 lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: `url('${moonImage}')` }}
        />
        <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(180deg,rgba(5,5,5,0.15)_0%,rgba(5,5,5,0.04)_52%,rgba(5,5,5,0.68)_100%)]" />

        <motion.div
          className="relative z-10"
          initial={reducedMotion ? false : { opacity: 0, transform: "translate3d(0, 8px, 0)" }}
          animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
          transition={{ duration: reducedMotion ? 0 : 0.5, ease: [0.23, 1, 0.32, 1] }}
        >
          <Brand />
        </motion.div>

        <motion.div
          className="relative z-10 max-w-xl pb-6"
          initial={reducedMotion ? false : { opacity: 0, transform: "translate3d(0, 14px, 0)" }}
          animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
          transition={{ duration: reducedMotion ? 0 : 0.58, delay: reducedMotion ? 0 : 0.1, ease: [0.23, 1, 0.32, 1] }}
        >
          <h1 className="max-w-lg text-4xl font-semibold leading-[1.08] tracking-[-0.035em] text-neutral-100 xl:text-5xl">
            Monitor dengan jelas. Bertindak dengan aman.
          </h1>
          <p className="mt-5 max-w-md text-base leading-7 text-neutral-300/80">
            Satu workspace untuk memahami kondisi sistem dan menangani hal yang membutuhkan keputusan supervisor.
          </p>
        </motion.div>
      </section>

      <section className="relative flex min-h-[100dvh] flex-col bg-[#080808] px-5 py-6 sm:px-10 sm:py-8 lg:justify-center lg:px-14 xl:px-20">
        <div className="mb-12 flex items-center lg:hidden">
          <Brand />
        </div>

        <motion.div
          className="mx-auto flex w-full max-w-[400px] flex-1 flex-col justify-center py-8 lg:flex-none lg:py-0"
          initial={reducedMotion ? false : { opacity: 0, transform: "translate3d(0, 12px, 0)" }}
          animate={{ opacity: 1, transform: "translate3d(0, 0, 0)" }}
          transition={{ duration: reducedMotion ? 0 : 0.5, delay: reducedMotion ? 0 : 0.08, ease: [0.23, 1, 0.32, 1] }}
        >
          <div className="inline-flex w-fit items-center gap-2 rounded-full border border-violet-300/15 bg-violet-300/[0.06] px-3 py-1.5 text-xs font-medium text-violet-200">
            <ShieldCheck className="h-3.5 w-3.5" /> Akses supervisor
          </div>
          <h2 className="mt-7 text-3xl font-semibold tracking-[-0.03em] text-neutral-100 sm:text-4xl">
            Masuk ke RAPIIN
          </h2>
          <p className="mt-3 text-sm leading-6 text-neutral-500">
            Gunakan akun organisasi Anda. Role dan izin ditentukan setelah autentikasi.
          </p>

          <form onSubmit={handleSubmit} noValidate className="mt-9 space-y-5">
            <div className="space-y-2">
              <label htmlFor="login-email" className="block text-sm font-medium text-neutral-300">
                Email
              </label>
              <input
                id="login-email"
                type="email"
                autoComplete="username"
                autoFocus
                value={email}
                disabled={isSubmitting}
                aria-invalid={Boolean(error) && !/^\S+@\S+\.\S+$/.test(email.trim())}
                onChange={(event) => {
                  setEmail(event.target.value);
                  setError("");
                }}
                placeholder="nama@perusahaan.com"
                className="h-12 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 text-sm text-neutral-100 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-neutral-600 focus:border-violet-300/50 focus:ring-2 focus:ring-violet-300/10 disabled:cursor-not-allowed disabled:opacity-60"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="login-password" className="block text-sm font-medium text-neutral-300">
                Kata Sandi
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type={passwordVisible ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  disabled={isSubmitting}
                  aria-invalid={Boolean(error) && password.length < 8}
                  aria-describedby={error ? "login-error" : "login-helper"}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setError("");
                  }}
                  placeholder="Masukkan kata sandi"
                  className="h-12 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-4 pr-12 text-sm text-neutral-100 outline-none transition-[border-color,box-shadow] duration-150 placeholder:text-neutral-600 focus:border-violet-300/50 focus:ring-2 focus:ring-violet-300/10 disabled:cursor-not-allowed disabled:opacity-60"
                />
                <button
                  type="button"
                  aria-label={passwordVisible ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                  aria-pressed={passwordVisible}
                  disabled={isSubmitting}
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  className="absolute right-1 top-1 inline-flex h-10 w-10 items-center justify-center rounded-md text-neutral-500 transition-colors hover:bg-neutral-900 hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 disabled:pointer-events-none"
                >
                  {passwordVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {!error && (
                <p id="login-helper" className="text-xs leading-5 text-neutral-600">
                  Minimal 8 karakter.
                </p>
              )}
              {error && (
                <p id="login-error" role="alert" className="text-sm leading-5 text-red-300">
                  {error}
                </p>
              )}
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className={cn(
                "flex h-12 w-full items-center justify-center gap-2 rounded-lg px-4 text-sm font-medium transition-[background-color,color,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#080808] active:scale-[0.985] disabled:cursor-wait",
                status === "success"
                  ? "bg-emerald-300 text-emerald-950"
                  : "bg-neutral-100 text-neutral-950 hover:bg-white",
              )}
            >
              {status === "idle" && (
                <>
                  Masuk <ArrowRight className="h-4 w-4" />
                </>
              )}
              {status === "loading" && (
                <>
                  <LoaderCircle className="h-4 w-4 animate-spin" /> Memverifikasi akun...
                </>
              )}
              {status === "success" && (
                <>
                  <CheckCircle2 className="h-4 w-4" /> Akun dikenali
                </>
              )}
            </button>
          </form>

          <div className="mt-8 border-t border-neutral-800 pt-5">
            <p className="flex items-start gap-2 text-xs leading-5 text-neutral-600">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-violet-300" />
              Kredensial Anda diverifikasi langsung oleh server RAPIIN.
            </p>
          </div>
        </motion.div>
      </section>
    </main>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <RapiinLogo className="text-neutral-100" />
      <div>
        <p className="text-sm font-medium tracking-tight text-neutral-100">RAPIIN</p>
        <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.14em] text-neutral-500">Asisten kerja</p>
      </div>
    </div>
  );
}
