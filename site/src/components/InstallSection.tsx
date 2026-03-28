import {motion} from "motion/react";

import {InstallTerminal} from "./InstallTerminal";
import {RevealOnScroll} from "./sitePrimitives";

export const InstallSection = () => {
  return (
    <section id="install" className="px-8 py-28 border-y border-white/5 bg-white/[0.02]">
      <div className="max-w-7xl mx-auto grid lg:grid-cols-[0.95fr_1.05fr] gap-14 items-center">
        <div>
          <RevealOnScroll>
            <h2 className="text-sm font-black uppercase tracking-[0.4em] text-accent mb-6">Install SOUL</h2>
          </RevealOnScroll>
          <RevealOnScroll delay={0.15}>
            <p className="text-4xl lg:text-5xl font-black tracking-tighter max-w-2xl">
              Start from one command, then drop straight into your terminal companion.
            </p>
          </RevealOnScroll>
          <RevealOnScroll delay={0.25}>
            <p className="mt-6 max-w-xl text-base lg:text-lg leading-relaxed text-text-muted">
              The installer targets the latest published release when available, falls back safely to the current main snapshot, and prints the next commands to get your local runtime ready.
            </p>
          </RevealOnScroll>
        </div>

        <RevealOnScroll delay={0.2}>
          <InstallTerminal />
        </RevealOnScroll>
      </div>
    </section>
  );
};
