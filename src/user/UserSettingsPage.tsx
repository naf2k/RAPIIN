"use client";

import { useEffect, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
import {
  Bell,
  Check,
  ChevronRight,
  Circle,
  CircleCheck,
  Info,
  Laptop,
  LogOut,
  Power,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { NotificationRows, useNotifications } from "@/components/ui/beresin-notifications";
import { ApiError, apiGet, apiPost, apiPut } from "@/lib/api";
import { clearSession, useSessionUser } from "@/lib/session";
import type { Device, Profile, UserSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

const surfaceClass = "rounded-xl border border-neutral-800 bg-neutral-900/35";

// The Desktop Agent reads this exact key from /api/agent/poll to manage OS autostart.
const STARTUP_MODE_KEY = "startup_mode";
const NOTIFICATION_KEYS = {
  completed: "notifications.task_completed",
  errors: "notifications.important_errors",
} as const;

function heartbeatLabel(lastHeartbeatAt: string | null): string {
  if (!lastHeartbeatAt) return "Belum pernah";
  const elapsedSeconds = Math.max(
    0,
    (Date.now() - new Date(lastHeartbeatAt).getTime()) / 1000,
  );
  if (elapsedSeconds < 60) return "Baru saja";
  const minutes = Math.round(elapsedSeconds / 60);
  if (minutes < 60) return `${minutes} mnt lalu`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} jam lalu`;
  return `${Math.round(hours / 24)} hari lalu`;
}

function connectionLabel(device: Device): string {
  if (device.status !== "ONLINE") return "Terputus";
  return device.connection_health === "DEGRADED" ? "Koneksi lemah" : "Terhubung";
}

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function UserSettingsPage() {
  const sessionUser = useSessionUser();
  const notificationFeed = useNotifications("user");
  const [autoStart, setAutoStart] = useState(false);
  const [notifications, setNotifications] = useState({ completed: true, errors: true });
  const [profile, setProfile] = useState<Profile | null>(null);
  const [device, setDevice] = useState<Device | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      apiGet<UserSettings>("/user/settings"),
      apiGet<Profile>("/user/profile"),
      apiGet<Device[]>("/user/devices"),
    ])
      .then(([settings, me, devices]) => {
        if (cancelled) return;
        setAutoStart(settings[STARTUP_MODE_KEY] === "auto");
        setNotifications({
          completed: settings[NOTIFICATION_KEYS.completed] !== "0",
          errors: settings[NOTIFICATION_KEYS.errors] !== "0",
        });
        setProfile(me);
        setDevice(devices[0] ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        // Keep the session-derived identity visible even if settings fail to load.
        setProfile(null);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const toggleNotification = (key: "completed" | "errors") => {
    setNotifications((current) => {
      const next = { ...current, [key]: !current[key] };
      apiPut("/user/settings", {
        key: NOTIFICATION_KEYS[key],
        value: next[key] ? "1" : "0",
      }).catch(() => undefined);
      return next;
    });
    setSaved(false);
  };

  const toggleAutoStart = () => {
    setAutoStart((current) => {
      apiPut("/user/settings", {
        key: STARTUP_MODE_KEY,
        value: current ? "manual" : "auto",
      }).catch(() => undefined);
      return !current;
    });
    setSaved(false);
  };

  const displayName = profile?.name ?? sessionUser?.name ?? "—";
  const displayEmail = profile?.email ?? sessionUser?.email ?? "—";

  return (
    <div className="h-full overflow-y-auto bg-neutral-950">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
        <PageIntro
          title="Pengaturan"
          description="Pengaturan BERESIN yang penting. Tidak ada konfigurasi teknis di sini."
          aside={<DemoLabel />}
        />

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="user-account-heading">
          <div className="flex items-center gap-3">
            <UserRound className="h-5 w-5 text-neutral-500" />
            <h2 id="user-account-heading" className="text-base font-medium text-neutral-100">Akun</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Nama" value={displayName} />
            <DefinitionRow label="Email" value={displayEmail} />
          </dl>
          <a
            href="/account"
            className="mt-5 inline-flex items-center gap-1.5 rounded-md text-sm text-neutral-400 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50"
          >
            Kelola akun <ChevronRight className="h-3.5 w-3.5" />
          </a>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="user-device-heading">
          <div className="flex items-center gap-3">
            <Laptop className="h-5 w-5 text-neutral-500" />
            <h2 id="user-device-heading" className="text-base font-medium text-neutral-100">Perangkat</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Perangkat" value={device?.device_name ?? "Belum ada device"} mono />
            <DefinitionRow
              label="Status"
              value={
                <span
                  className={cn(
                    "inline-flex items-center gap-2",
                    !device
                      ? "text-neutral-500"
                      : device.status !== "ONLINE"
                        ? "text-neutral-400"
                        : device.connection_health === "DEGRADED"
                          ? "text-amber-300"
                          : "text-emerald-300",
                  )}
                >
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      !device
                        ? "bg-neutral-600"
                        : device.status !== "ONLINE"
                          ? "bg-neutral-500"
                          : device.connection_health === "DEGRADED"
                            ? "bg-amber-400"
                            : "bg-emerald-400",
                    )}
                    aria-hidden="true"
                  />
                  {device ? connectionLabel(device) : "Belum terdaftar"}
                </span>
              }
            />
            <DefinitionRow label="Versi agent" value={device?.agent_version ?? "Belum terpasang"} mono />
            <DefinitionRow label="Sistem operasi" value={device?.os ?? "Tidak diketahui"} />
            <DefinitionRow
              label="Heartbeat terakhir"
              value={heartbeatLabel(device?.last_heartbeat_at ?? null)}
            />
          </dl>
          <div className="mt-5 rounded-lg border border-neutral-800 bg-neutral-950 p-4">
            <p className="text-sm font-medium text-neutral-200">Pasang Agent di PC Windows</p>
            <p className="mt-1 text-[13px] leading-5 text-neutral-500">
              Chat di sini lewat browser. Supaya BERESIN bisa mengerjakan file di PC, pasang Agent-nya
              (butuh Python 3.12+, <span className="font-mono text-xs text-neutral-400">uv</span>, dan Tailscale
              satu tailnet dengan server). Buka Git Bash lalu:
            </p>
            <ol className="mt-3 space-y-2 text-[13px] leading-5 text-neutral-400">
              <li>
                <span className="text-neutral-500">1. Pasang wheel rilis (cek checksum dulu):</span>
                <code className="mt-1 block overflow-x-auto rounded-md bg-neutral-900 px-3 py-2 font-mono text-xs text-neutral-300">
                  uv tool install beresin_agent-1.0.0-py3-none-any.whl
                </code>
              </li>
              <li>
                <span className="text-neutral-500">2. Daftarkan device ini (pilih auto supaya hidup sendiri tiap PC nyala):</span>
                <code className="mt-1 block overflow-x-auto rounded-md bg-neutral-900 px-3 py-2 font-mono text-xs text-neutral-300">
                  beresin setup --server https://NAMA-SERVER.ts.net --autostart
                </code>
              </li>
              <li>
                <span className="text-neutral-500">3. Verifikasi:</span>
                <code className="mt-1 block overflow-x-auto rounded-md bg-neutral-900 px-3 py-2 font-mono text-xs text-neutral-300">
                  beresin verify
                </code>
              </li>
            </ol>
          </div>
        </section>

        <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="user-startup-heading">
          <div className="border-b border-neutral-800 px-5 py-4 sm:px-6">
            <div className="flex items-center gap-3">
              <Power className="h-5 w-5 text-neutral-500" />
              <h2 id="user-startup-heading" className="text-base font-medium text-neutral-100">Startup</h2>
            </div>
            <p className="mt-1 text-sm text-neutral-500">Mode berjalan: {autoStart ? "Otomatis" : "Manual"}.</p>
          </div>
          <ToggleRow
            label="Jalankan BERESIN otomatis saat komputer menyala"
            description="Agent berjalan sebagai background service dan reconnect aman tanpa membuka terminal."
            checked={autoStart}
            onChange={toggleAutoStart}
          />
        </section>

        <section className={cn(surfaceClass, "overflow-hidden")} aria-labelledby="user-notifications-heading">
          <div className="border-b border-neutral-800 px-5 py-4 sm:px-6">
            <div className="flex items-center gap-3">
              <Bell className="h-5 w-5 text-neutral-500" />
              <h2 id="user-notifications-heading" className="text-base font-medium text-neutral-100">Notifikasi</h2>
            </div>
            <p className="mt-1 text-sm text-neutral-500">Hanya hal penting yang diberi tahu.</p>
          </div>
          <div className="divide-y divide-neutral-800">
            <ToggleRow
              label="Tugas selesai"
              description="Saat pekerjaan yang diminta selesai dan terverifikasi."
              checked={notifications.completed}
              onChange={() => toggleNotification("completed")}
            />
            <ToggleRow
              label="Error penting"
              description="Saat BERESIN tidak bisa menyelesaikan pekerjaan."
              checked={notifications.errors}
              onChange={() => toggleNotification("errors")}
            />
          </div>
          <div className="border-t border-neutral-800">
            <div className="flex items-center justify-between px-5 py-3 sm:px-6">
              <p className="text-xs font-medium uppercase tracking-[0.12em] text-neutral-600">Terbaru</p>
              {notificationFeed.unread > 0 && (
                <span className="text-xs text-neutral-500">
                  {notificationFeed.unread} belum dibaca
                </span>
              )}
            </div>
            <NotificationRows
              items={notificationFeed.items.slice(0, 5)}
              onRead={notificationFeed.markRead}
            />
          </div>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="user-about-heading">
          <div className="flex items-center gap-3">
            <Info className="h-5 w-5 text-neutral-500" />
            <h2 id="user-about-heading" className="text-base font-medium text-neutral-100">Tentang</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Versi BERESIN" value="1.0.0" mono />
            <DefinitionRow label="Antarmuka" value="Chat Pengguna" />
            <DefinitionRow label="Lingkungan" value="Server BERESIN" />
          </dl>
        </section>

        <div className="flex items-center justify-end gap-4">
          {saved && (
            <span role="status" className="inline-flex items-center gap-2 text-sm text-emerald-300">
              <Check className="h-4 w-4" /> Tersimpan
            </span>
          )}
          <Button
            type="button"
            onClick={() => setSaved(true)}
            className="bg-neutral-100 text-neutral-950 hover:bg-white active:scale-[0.98]"
          >
            Simpan perubahan
          </Button>
        </div>
      </div>
    </div>
  );
}

export function UserAccountPage() {
  const sessionUser = useSessionUser();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [device, setDevice] = useState<Device | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([apiGet<Profile>("/user/profile"), apiGet<Device[]>("/user/devices")])
      .then(([me, devices]) => {
        if (cancelled) return;
        setProfile(me);
        setDevice(devices[0] ?? null);
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = (event: MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    apiPost("/auth/logout").catch(() => undefined);
    clearSession();
    window.location.assign("/login");
  };

  const displayName = profile?.name ?? sessionUser?.name ?? "—";
  const displayEmail = profile?.email ?? sessionUser?.email ?? "—";
  const displayRole = profile?.role ?? sessionUser?.role ?? "USER";

  return (
    <div className="h-full overflow-y-auto bg-neutral-950">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-7 px-4 py-6 sm:px-6 sm:py-8 lg:px-10 lg:py-10">
        <PageIntro
          title="Akun"
          description="Identitas dan sesi Anda di BERESIN."
          aside={<DemoLabel />}
        />

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="profile-heading">
          <div className="flex items-center gap-4 border-b border-neutral-800 pb-5">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-violet-400/10 text-sm font-semibold text-violet-200">
              {initialsOf(displayName) || "—"}
            </div>
            <div>
              <h2 id="profile-heading" className="text-base font-medium text-neutral-100">{displayName}</h2>
              <p className="mt-1 text-sm text-neutral-500">
                {displayRole === "SUPERVISOR" ? "Supervisor" : "Pengguna"}
              </p>
            </div>
          </div>
          <dl className="mt-2 divide-y divide-neutral-800">
            <DefinitionRow label="Nama" value={displayName} />
            <DefinitionRow label="Email" value={displayEmail} />
            <DefinitionRow label="Role" value={displayRole} mono />
            <DefinitionRow label="Perangkat" value={device?.device_name ?? "Belum ada device"} mono />
          </dl>
        </section>

        <section className={cn(surfaceClass, "p-5 sm:p-6")} aria-labelledby="session-heading">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-violet-300" />
            <h2 id="session-heading" className="text-base font-medium text-neutral-100">Sesi & keamanan</h2>
          </div>
          <dl className="mt-5 divide-y divide-neutral-800">
            <DefinitionRow label="Sesi saat ini" value="Browser ini" />
            <DefinitionRow
              label="Status sesi"
              value={
                <span className="inline-flex items-center gap-2 text-emerald-300">
                  <CircleCheck className="h-4 w-4" /> Aman
                </span>
              }
            />
            <DefinitionRow
              label="Perangkat terdaftar"
              value={device ? connectionLabel(device) : "Belum terdaftar"}
            />
          </dl>
        </section>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-5 text-neutral-600">Keluar akan mengakhiri sesi di browser ini.</p>
          <a
            href="/login"
            onClick={handleLogout}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-neutral-700 bg-transparent px-4 text-sm font-medium text-neutral-200 transition-colors hover:bg-neutral-900 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400/50 active:scale-[0.98]"
          >
            <LogOut className="h-4 w-4" /> Keluar
          </a>
        </div>
      </div>
    </div>
  );
}

function PageIntro({ title, description, aside }: { title: string; description: string; aside?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.025em] text-neutral-100 sm:text-3xl">{title}</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-neutral-500 sm:text-base">{description}</p>
      </div>
      {aside}
    </div>
  );
}

function DemoLabel() {
  return (
    <span className="inline-flex w-fit items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/60 px-3 py-1.5 text-xs text-neutral-500">
      <Circle className="h-2 w-2 fill-violet-300 text-violet-300" /> Data langsung
    </span>
  );
}

function DefinitionRow({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="grid gap-1 py-3 first:pt-0 last:pb-0 sm:grid-cols-[150px_minmax(0,1fr)] sm:gap-4">
      <dt className="text-sm text-neutral-600">{label}</dt>
      <dd className={cn("text-sm text-neutral-300 sm:text-right", mono && "font-mono text-xs")}>{value}</dd>
    </div>
  );
}

function ToggleRow({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: () => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-5 px-5 py-4 sm:px-6">
      <span>
        <span className="block text-sm font-medium text-neutral-200">{label}</span>
        <span className="mt-1 block text-sm leading-6 text-neutral-500">{description}</span>
      </span>
      <span className="relative inline-flex h-6 w-11 flex-shrink-0">
        <input type="checkbox" checked={checked} onChange={onChange} className="peer sr-only" />
        <span className="absolute inset-0 rounded-full bg-neutral-700 transition-colors duration-150 peer-checked:bg-violet-500 peer-focus-visible:ring-2 peer-focus-visible:ring-violet-300 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-neutral-950" />
        <span className="absolute left-1 top-1 h-4 w-4 rounded-full bg-white transition-transform duration-150 peer-checked:translate-x-5" />
      </span>
    </label>
  );
}
