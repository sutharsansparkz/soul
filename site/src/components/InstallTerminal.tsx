import {Check, Copy, Terminal} from "lucide-react";
import {motion} from "motion/react";
import {useEffect, useState} from "react";

const FALLBACK_INSTALL_URL = "https://sparkz-technology.github.io/soul/install.sh";

const getInstallCommand = () => {
  if (typeof window === "undefined") {
    return `curl -fsSL ${FALLBACK_INSTALL_URL} | bash`;
  }

  const installUrl = new URL(`${import.meta.env.BASE_URL}install.sh`, window.location.origin).toString();
  return `curl -fsSL ${installUrl} | bash`;
};

export const InstallTerminal = () => {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const installCommand = getInstallCommand();

  useEffect(() => {
    if (copyState === "idle") {
      return;
    }

    const timeout = window.setTimeout(() => setCopyState("idle"), 2200);
    return () => window.clearTimeout(timeout);
  }, [copyState]);

  const handleCopyInstallCommand = async () => {
    if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
      setCopyState("error");
      return;
    }

    try {
      await navigator.clipboard.writeText(installCommand);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  return (
    <motion.div
      initial={{opacity: 0, y: 18}}
      animate={{opacity: 1, y: 0}}
      transition={{duration: 0.9, delay: 0.2, ease: "easeOut"}}
      className="terminal-window relative z-10 ml-auto max-w-xl"
    >
      <div className="bg-surface px-4 py-3 border-b border-white/5 flex items-center justify-between">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/40" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/40" />
          <div className="w-3 h-3 rounded-full bg-green-500/40" />
        </div>
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest flex items-center gap-2">
          <Terminal className="w-3 h-3" /> install.sh
        </div>
      </div>
      <div className="relative p-6 font-mono">
        <div className="scanline" />
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-text-muted">
            <Terminal className="h-3.5 w-3.5 text-accent" />
            One-Line Install
          </div>
          <button
            type="button"
            onClick={handleCopyInstallCommand}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-white/85 transition hover:border-accent/30 hover:bg-accent/10 hover:text-accent"
          >
            {copyState === "copied" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy Manually" : "Copy"}
          </button>
        </div>
        <div className="overflow-x-auto rounded-xl border border-white/6 bg-[#111214] px-4 py-3">
          <div className="whitespace-nowrap text-[12px] text-accent">
            <span className="mr-2 text-text-muted">$</span>
            {installCommand}
          </div>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-text-muted">
          Installs the latest SOUL release from this site and keeps the command ready to copy.
        </p>
      </div>
    </motion.div>
  );
};
