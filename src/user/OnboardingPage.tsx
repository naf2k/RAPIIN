"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  Laptop,
  LoaderCircle,
  Play,
  ShieldCheck,
  UserRound,
  Zap,
} from "lucide-react";

import { RapiinLogo } from "@/components/ui/rapiin-logo";
import { ApiError, apiPost, apiPut } from "@/lib/api";
import { useSessionUser } from "@/lib/session";
import { cn } from "@/lib/utils";

type StepId = "welcome" | "account" | "device" | "verify" | "startup" | "done";

const STEPS: Array<{ id: StepId; label: string }> = [
  { id: "welcome", label: "Mulai" },
  { id: "account", label: "Akun" },
  { id: "device", label: "Device" },
  { id: "verify", label: "Verifikasi" },
  { id: "startup", label: "Startup" },
  { id: "done", label: "Selesai" },
];

const DEVICE_NAME_KEY = "rapiin.device.name";

function detectOs(): string {
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return "Windows";
  if (/Mac OS X|Macintosh/i.test(ua)) return "macOS";
  if (/Android/i.test(ua)) return "Android";
  if (/iPhone|iPad|iPod/i.test(ua)) return "iOS";
  if (/Linux/i.test(ua)) return "Linux";
  return "Tidak diketahui";
}

/** A stable per-browser device name so re-pairing rotates the key instead of duplicating devices. */
function resolveDeviceName(): string {
  try {
    const existing = window.localStorage.getItem(DEVICE_NAME_KEY);
    if (existing) return existing;
  } catch {
    // Storage unavailable; fall through to a one-off name.
  }
  const suggested = `PC-WEB-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
  try {
    window.localStorage.setItem(DEVICE_NAME_KEY, suggested);
  } catch {
    return suggested;
  }
  return suggested;
}

export default function OnboardingPage() {
  const user = useSessionUser();
  const [stepIndex, setStepIndex] = useState(0);
  const [startupMode, setStartupMode] = useState<"manual" | "auto">("manual");
  const [verified, setVerified] = useState<[boolean, boolean]>([false, false]);
  const [device, setDevice] = useState<{ name: string; os: string }>(() => ({
    name: resolveDeviceName(),
    os: detectOs(),
  }));
  const [registered, setRegistered] = useState(false);
  const [error, setError] = useState("");
  const titleRef = useRef<HTMLHeadingElement>(null);
  const step = STEPS[stepIndex].id;
  const initials = (user?.name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  useEffect(() => {
    const previousTitle = document.title;
    document.title = "Setup | RAPIIN";
    return () => {
      document.title = previousTitle;
    };
  }, []);

  useEffect(() => {
    titleRef.current?.focus({ preventScroll: true });
  }, [stepIndex]);

  useEffect(() => {
    if (step !== "verify") return;
    let cancelled = false;
    const timers: number[] = [];
    setError("");
    setVerified([false, false]);

    apiPost<{ device_id: number; device_key: string }>("/auth/register-device", {
      device_name: device.name,
      os: device.os,
      agent_version: null,
    })
      .then(() => {
        if (cancelled) return;
        setVerified([true, false]);
        setRegistered(true);
        timers.push(
          window.setTimeout(() => setVerified([true, true]), 450),
        );
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setError(
          cause instanceof ApiError
            ? cause.message
            : "Gagal mendaftarkan device. Coba lagi.",
        );
      });

    return () => {
      cancelled = true;
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [step, device.name, device.os]);

  useEffect(() => {
    if (step !== "verify" || !verified[0] || !verified[1]) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
      return;
    }
    const timer = window.setTimeout(() => {
      setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
    }, 900);
    return () => window.clearTimeout(timer);
  }, [step, verified]);

  useEffect(() => {
    if (step !== "done") return;
    apiPut("/user/settings", { key: "startup_mode", value: startupMode }).catch(
      () => undefined,
    );
  }, [step, startupMode]);

  const go = (index: number) => {
    setStepIndex(Math.max(0, Math.min(index, STEPS.length - 1)));
    window.scrollTo({ top: 0 });
  };

  const finish = () => {
    window.location.replace("/");
  };

  return (
    <main className="dark min-h-[100dvh] bg-[#050505] text-neutral-100">
      <div className="mx-auto flex min-h-[100dvh] w-full max-w-2xl flex-col px-4 py-6 sm:px-6 sm:py-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <RapiinLogo className="text-neutral-100" />
            <p className="text-sm font-medium tracking-tight text-neutral-100">RAPIIN</p>
          </div>
          <p className="text-xs text-neutral-600">Setup awal</p>
        </div>

        <Stepper current={stepIndex} />

        <div className="mt-6 rounded-2xl border border-neutral-800 bg-[#080808] p-6 sm:p-8">
          {step === "welcome" && (
            <section aria-labelledby="onboarding-title">
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none sm:text-3xl"
              >
                Selamat datang di RAPIIN.
              </h1>
              <p className="mt-3 text-sm leading-6 text-neutral-500 sm:text-base">
                Bilang apa yang ingin dikerjakan, RAPIIN yang mengerjakan. Siapkan dulu dalam tiga langkah cepat.
              </p>
              <ul className="mt-6 space-y-3">
                <WelcomeRow icon={<UserRound className="h-4 w-4" />} title="Masuk dengan akun" detail={user?.email ?? "Akun RAPIIN Anda"} />
                <WelcomeRow icon={<Laptop className="h-4 w-4" />} title="Daftarkan device" detail={`${device.name} · ${device.os}`} />
                <WelcomeRow icon={<Zap className="h-4 w-4" />} title="Pilih mode startup" detail="Manual atau otomatis saat komputer menyala." />
              </ul>
              <div className="mt-8 flex justify-end">
                <PrimaryButton onClick={() => go(stepIndex + 1)}>
                  Mulai setup <ArrowRight className="h-4 w-4" />
                </PrimaryButton>
              </div>
            </section>
          )}

          {step === "account" && (
            <section aria-labelledby="onboarding-title">
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none"
              >
                Masuk dengan akun Anda.
              </h1>
              <p className="mt-3 text-sm leading-6 text-neutral-500">
                Satu akun, satu device. Memory dan file Anda terisolasi dari user lain.
              </p>
              <div className="mt-6 flex items-center gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-4">
                <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl bg-violet-400/10 text-sm font-semibold text-violet-200">
                  {initials || "—"}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-neutral-100">{user?.name ?? "Pengguna RAPIIN"}</p>
                  <p className="mt-0.5 truncate text-sm text-neutral-500">{user?.email ?? "Sesi aktif"}</p>
                </div>
              </div>
              <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-neutral-600">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-violet-300" />
                Sesi ini terautentikasi oleh server RAPIIN. Memory dan file Anda terisolasi dari user lain.
              </p>
              <StepNav onBack={() => go(stepIndex - 1)} onNext={() => go(stepIndex + 1)} nextLabel="Lanjutkan" />
            </section>
          )}

          {step === "device" && (
            <section aria-labelledby="onboarding-title">
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none"
              >
                Daftarkan device ini.
              </h1>
              <p className="mt-3 text-sm leading-6 text-neutral-500">
                Setiap device punya identitas unik agar server tahu siapa yang online dan sehat.
              </p>
              <dl className="mt-6 divide-y divide-neutral-800 rounded-xl border border-neutral-800 bg-neutral-950 px-4">
                <DefinitionRow label="Device" value={device.name} mono />
                <DefinitionRow label="Operating system" value={device.os} />
                <DefinitionRow label="Agent version" value="Belum terpasang" />
                <DefinitionRow label="Status" value={registered ? "Terdaftar" : "Belum terdaftar"} />
              </dl>
              <p className="mt-4 flex items-start gap-2 rounded-lg border border-neutral-800 bg-neutral-950 px-4 py-3 text-xs leading-5 text-neutral-500">
                <ShieldCheck className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-violet-300" />
                Browser ini baru terdaftar sebagai identitas. Supaya RAPIIN bisa mengerjakan file di PC
                Windows, pasang juga Agent-nya (Git Bash): uv tool install wheel rilis, lalu rapiin setup
                --server https://NAMA-SERVER.ts.net --autostart, lalu rapiin verify. Panduan lengkap ada
                di halaman Pengaturan → Perangkat.
              </p>
              <StepNav onBack={() => go(stepIndex - 1)} onNext={() => go(stepIndex + 1)} nextLabel="Daftarkan device" />
            </section>
          )}

          {step === "verify" && (
            <section aria-labelledby="onboarding-title">
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none"
              >
                Memverifikasi device…
              </h1>
              <p className="mt-3 text-sm leading-6 text-neutral-500">
                Mendaftarkan identitas dan membuka koneksi aman ke server.
              </p>
              <ul className="mt-6 space-y-3" role="status" aria-label="Status verifikasi">
                <VerifyRow done={verified[0]} label="Device terdaftar" />
                <VerifyRow done={verified[1]} label="Koneksi aman dibuat" />
              </ul>
              {error && (
                <p role="alert" className="mt-4 text-sm leading-5 text-red-300">
                  {error}
                </p>
              )}
              {verified[0] && verified[1] && (
                <div className="mt-8 flex justify-end">
                  <PrimaryButton onClick={() => go(stepIndex + 1)}>
                    Lanjut <ArrowRight className="h-4 w-4" />
                  </PrimaryButton>
                </div>
              )}
            </section>
          )}

          {step === "startup" && (
            <section aria-labelledby="onboarding-title">
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none"
              >
                Pilih mode startup.
              </h1>
              <p className="mt-3 text-sm leading-6 text-neutral-500">
                Bisa diubah kapan saja dari Settings.
              </p>
              <div className="mt-6 grid gap-3" role="radiogroup" aria-label="Mode startup">
                <StartupOption
                  selected={startupMode === "manual"}
                  onSelect={() => setStartupMode("manual")}
                  icon={<Play className="h-4 w-4" />}
                  title="Manual"
                  detail="Jalankan rapiin saat dibutuhkan. Tidak otomatis berjalan saat komputer menyala."
                />
                <StartupOption
                  selected={startupMode === "auto"}
                  onSelect={() => setStartupMode("auto")}
                  icon={<Zap className="h-4 w-4" />}
                  title="Otomatis"
                  detail="Agent berjalan sebagai background service dan reconnect aman tanpa membuka terminal."
                />
              </div>
              <StepNav onBack={() => go(stepIndex - 1)} onNext={() => go(stepIndex + 1)} nextLabel="Selesai" />
            </section>
          )}

          {step === "done" && (
            <section aria-labelledby="onboarding-title" className="text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-400/10">
                <CheckCircle2 className="h-7 w-7 text-emerald-300" />
              </div>
              <h1
                id="onboarding-title"
                ref={titleRef}
                tabIndex={-1}
                className="mt-5 text-2xl font-semibold tracking-[-0.025em] text-neutral-100 outline-none"
              >
                RAPIIN Agent ready.
              </h1>
              <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-neutral-500">
                Akun terautentikasi, device terdaftar, koneksi aman. Mulai ngomong, RAPIIN yang mengerjakan.
              </p>
              <dl className="mx-auto mt-6 max-w-md divide-y divide-neutral-800 rounded-xl border border-neutral-800 bg-neutral-950 px-4 text-left">
                <DefinitionRow label="Account" value={user?.email ?? "Sesi aktif"} />
                <DefinitionRow label="Device" value={device.name} mono />
                <DefinitionRow label="Startup" value={startupMode === "auto" ? "Otomatis" : "Manual"} />
              </dl>
              <div className="mt-8 flex justify-center">
                <PrimaryButton onClick={finish}>
                  Mulai chat <ArrowRight className="h-4 w-4" />
                </PrimaryButton>
              </div>
            </section>
          )}
        </div>

        <p className="mt-6 text-center text-xs leading-5 text-neutral-700">
          Device ini akan dipakai RAPIIN untuk menjalankan pekerjaan file Anda.
        </p>
      </div>
    </main>
  );
}

function Stepper({ current }: { current: number }) {
  return (
    <div className="mt-8">
      <ol className="flex items-center" aria-label="Langkah setup">
        {STEPS.map((item, index) => {
          const state = index < current ? "done" : index === current ? "current" : "todo";
          return (
            <li key={item.id} className={cn("flex items-center", index < STEPS.length - 1 && "flex-1")}>
              <span
                aria-current={state === "current" ? "step" : undefined}
                className="flex items-center gap-2"
                title={item.label}
              >
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-medium",
                    state === "done" && "bg-emerald-400/15 text-emerald-300",
                    state === "current" && "bg-neutral-100 text-neutral-950",
                    state === "todo" && "bg-neutral-800 text-neutral-500",
                  )}
                >
                  {state === "done" ? <Check className="h-3 w-3" /> : index + 1}
                </span>
                <span
                  className={cn(
                    "hidden text-xs sm:block",
                    state === "current" ? "font-medium text-neutral-100" : "text-neutral-600",
                  )}
                >
                  {item.label}
                </span>
              </span>
              {index < STEPS.length - 1 && (
                <span
                  aria-hidden="true"
                  className={cn("mx-2 h-px flex-1 sm:mx-3", index < current ? "bg-emerald-400/40" : "bg-neutral-800")}
                />
              )}
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs text-neutral-600 sm:hidden" aria-hidden="true">
        Langkah {current + 1} dari {STEPS.length} · {STEPS[current].label}
      </p>
    </div>
  );
}

function WelcomeRow({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return (
    <li className="flex items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-950 px-4 py-3">
      <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-violet-400/10 text-violet-200">
        {icon}
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-neutral-100">{title}</span>
        <span className="mt-0.5 block truncate text-xs text-neutral-500">{detail}</span>
      </span>
    </li>
  );
}

function VerifyRow({ done, label }: { done: boolean; label: string }) {
  return (
    <li
      className={cn(
        "flex items-center gap-3 rounded-xl border px-4 py-3.5",
        done ? "border-emerald-400/20 bg-emerald-400/[0.04]" : "border-neutral-800 bg-neutral-950",
      )}
    >
      {done ? (
        <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-300" aria-hidden="true" />
      ) : (
        <LoaderCircle className="h-4 w-4 flex-shrink-0 animate-spin text-violet-300" aria-hidden="true" />
      )}
      <span className={cn("text-sm", done ? "text-neutral-100" : "text-neutral-500")}>{label}</span>
    </li>
  );
}

function StartupOption({
  selected,
  onSelect,
  icon,
  title,
  detail,
}: {
  selected: boolean;
  onSelect: () => void;
  icon: React.ReactNode;
  title: string;
  detail: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cn(
        "flex items-start gap-4 rounded-xl border p-4 text-left transition-[border-color,background-color,transform] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.99]",
        selected
          ? "border-violet-400/60 bg-violet-400/[0.06]"
          : "border-neutral-800 bg-neutral-950 hover:border-neutral-700",
      )}
    >
      <span
        className={cn(
          "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg",
          selected ? "bg-violet-400/15 text-violet-200" : "bg-neutral-900 text-neutral-500",
        )}
      >
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-neutral-100">{title}</span>
        <span className="mt-1 block text-[13px] leading-5 text-neutral-500">{detail}</span>
      </span>
      <span
        aria-hidden="true"
        className={cn(
          "mt-1 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border",
          selected ? "border-violet-300 bg-violet-400 text-neutral-950" : "border-neutral-700",
        )}
      >
        {selected && <Check className="h-3 w-3" strokeWidth={3} />}
      </span>
    </button>
  );
}

function StepNav({ onBack, onNext, nextLabel }: { onBack: () => void; onNext: () => void; nextLabel: string }) {
  return (
    <div className="mt-8 flex items-center justify-between gap-3">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex h-11 items-center gap-1.5 rounded-lg px-3 text-sm text-neutral-500 transition-colors hover:text-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
      >
        <ChevronLeft className="h-4 w-4" /> Kembali
      </button>
      <PrimaryButton onClick={onNext}>
        {nextLabel} <ArrowRight className="h-4 w-4" />
      </PrimaryButton>
    </div>
  );
}

function PrimaryButton({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-neutral-100 px-5 text-sm font-medium text-neutral-950 transition-[background-color,transform] hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-300 active:scale-[0.98]"
    >
      {children}
    </button>
  );
}

function DefinitionRow({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="grid gap-1 py-3 first:pt-3 last:pb-3 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm text-neutral-600">{label}</dt>
      <dd className={cn("text-sm text-neutral-300 sm:text-right", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}
