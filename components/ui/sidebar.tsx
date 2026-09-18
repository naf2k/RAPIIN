"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Menu, X } from "lucide-react";
import { createContext, useContext, useState } from "react";
import type { AnchorHTMLAttributes, ComponentProps, Dispatch, ReactNode, SetStateAction } from "react";

import { cn } from "@/lib/utils";

interface Links {
  label: string;
  href: string;
  icon?: ReactNode;
}

interface SidebarContextProps {
  open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>;
  animate: boolean;
}

const SidebarContext = createContext<SidebarContextProps | undefined>(undefined);

export const useSidebar = () => {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
};

export const SidebarProvider = ({
  children,
  open: openProp,
  setOpen: setOpenProp,
  animate = true,
}: {
  children: ReactNode;
  open?: boolean;
  setOpen?: Dispatch<SetStateAction<boolean>>;
  animate?: boolean;
}) => {
  const [openState, setOpenState] = useState(false);

  const open = openProp !== undefined ? openProp : openState;
  const setOpen = setOpenProp !== undefined ? setOpenProp : setOpenState;

  return (
    <SidebarContext.Provider value={{ open, setOpen, animate }}>
      {children}
    </SidebarContext.Provider>
  );
};

export const Sidebar = ({
  children,
  open,
  setOpen,
  animate,
}: {
  children: ReactNode;
  open?: boolean;
  setOpen?: Dispatch<SetStateAction<boolean>>;
  animate?: boolean;
}) => {
  return (
    <SidebarProvider open={open} setOpen={setOpen} animate={animate}>
      {children}
    </SidebarProvider>
  );
};

export const SidebarBody = (props: ComponentProps<typeof motion.div>) => {
  return (
    <>
      <DesktopSidebar {...props} />
      <MobileSidebar {...(props as ComponentProps<"div">)} />
    </>
  );
};

export const DesktopSidebar = ({
  className,
  children,
  ...props
}: ComponentProps<typeof motion.div>) => {
  const { open, setOpen, animate } = useSidebar();
  const expanded = !animate || open;

  return (
    <motion.div
      className="relative z-30 hidden h-full w-[60px] flex-shrink-0 self-stretch md:block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocusCapture={() => setOpen(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      {...props}
    >
      <motion.div
        data-expanded={expanded}
        className={cn(
          "absolute inset-y-0 left-0 flex w-[240px] flex-col overflow-hidden border-r border-transparent bg-neutral-950 px-4 py-4",
          "[clip-path:inset(0_180px_0_0)] transition-[clip-path,border-color,box-shadow] duration-[260ms] ease-[cubic-bezier(0.23,1,0.32,1)]",
          "data-[expanded=true]:[clip-path:inset(0_0_0_0)] data-[expanded=true]:border-neutral-800 data-[expanded=true]:shadow-[18px_0_32px_-24px_rgba(0,0,0,0.95)]",
          className,
        )}
      >
        {children}
      </motion.div>
    </motion.div>
  );
};

export const MobileSidebar = ({
  className,
  children,
  ...props
}: ComponentProps<"div">) => {
  const { open, setOpen } = useSidebar();

  return (
    <>
      <div
        className={cn(
          "flex h-12 w-full flex-shrink-0 flex-row items-center justify-end bg-neutral-950 px-3 md:hidden",
        )}
        {...props}
      >
        <button
          type="button"
          aria-label="Buka sidebar"
          className="z-20 inline-flex h-10 w-10 items-center justify-center rounded-lg text-neutral-200 transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
          onClick={() => setOpen(!open)}
        >
          <Menu
            className="h-5 w-5"
          />
        </button>
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ x: "-100%", opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: "-100%", opacity: 0 }}
              transition={{
                duration: 0.3,
                ease: "easeInOut",
              }}
              className={cn(
                "fixed inset-0 z-[100] flex h-[100dvh] w-full flex-col justify-between bg-neutral-950 p-10",
                className,
              )}
            >
              <button
                type="button"
                aria-label="Tutup sidebar"
                className="absolute right-6 top-6 z-50 inline-flex h-10 w-10 items-center justify-center rounded-lg text-neutral-200 transition-colors hover:bg-neutral-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-500"
                onClick={() => setOpen(!open)}
              >
                <X className="h-5 w-5" />
              </button>
              {children}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
};

export const SidebarLink = ({
  link,
  className,
  ...props
}: {
  link: Links;
  className?: string;
} & AnchorHTMLAttributes<HTMLAnchorElement>) => {
  const { open, animate } = useSidebar();
  const labelVisible = !animate || open;

  return (
    <a
      href={link.href}
      aria-label={link.label}
      className={cn(
        "flex items-center justify-start gap-2 group/sidebar py-2",
        className,
      )}
      {...props}
    >
      {link.icon}
      <span
        aria-hidden={animate && !open}
        className={cn(
          "inline-block whitespace-pre text-sm text-neutral-300 transition-[opacity,transform] ease-[cubic-bezier(0.23,1,0.32,1)] !m-0 !p-0",
          labelVisible
            ? "translate-x-0 opacity-100 delay-75 duration-200"
            : "pointer-events-none -translate-x-1.5 opacity-0 delay-0 duration-100",
        )}
      >
        {link.label}
      </span>
    </a>
  );
};
