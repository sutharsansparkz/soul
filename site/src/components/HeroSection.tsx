import {motion, useScroll, useTransform} from "motion/react";
import {ArrowRight, Github, Sparkles} from "lucide-react";
import {useRef} from "react";

import {GITHUB_REPOSITORY_URL} from "../hooks/useRepoSnapshot";
import {MagneticButton, TextReveal} from "./sitePrimitives";
import {SoulCore, TerminalPreview} from "./SiteScene";

export const HeroSection = () => {
  const heroRef = useRef<HTMLElement>(null);
  const {scrollY} = useScroll();
  const y1 = useTransform(scrollY, [0, 500], [0, 200]);
  const opacity = useTransform(scrollY, [0, 300], [1, 0]);

  return (
    <header ref={heroRef} className="relative min-h-[100svh] px-8 pt-28 pb-14 md:pt-32 md:pb-16 flex items-center overflow-hidden">
      <div className="w-full max-w-7xl mx-auto grid lg:grid-cols-2 gap-20 items-center">
        <motion.div style={{y: y1, opacity}}>
          <motion.div
            initial={{opacity: 0, scale: 0.8}}
            animate={{opacity: 1, scale: 1}}
            className="inline-flex items-center gap-3 px-4 py-2 rounded-full bg-accent-muted border border-accent/20 text-accent text-xs font-black uppercase tracking-[0.2em] mb-8"
          >
            <Sparkles className="w-4 h-4 animate-pulse" />
            Terminal-First AI
          </motion.div>

          <h1 className="text-6xl lg:text-8xl font-black leading-[0.9] tracking-tighter mb-8">
            <TextReveal text="THE AI WITH" className="block" />
            <TextReveal text="A MEMORY." className="block text-accent text-glow" />
          </h1>

          <motion.p
            initial={{opacity: 0}}
            animate={{opacity: 1}}
            transition={{delay: 0.6}}
            className="text-xl text-text-muted leading-relaxed mb-12 max-w-xl font-medium"
          >
            SOUL is a persistent companion that lives in your terminal. It remembers your past, adapts to your mood, and evolves over time.
          </motion.p>

          <motion.div initial={{opacity: 0, y: 20}} animate={{opacity: 1, y: 0}} transition={{delay: 0.8}} className="flex flex-wrap gap-6">
            <MagneticButton href={GITHUB_REPOSITORY_URL} className="btn-primary flex items-center gap-3">
              View Repository <Github className="w-6 h-6" />
            </MagneticButton>
            <a href="#features" className="btn-secondary flex items-center gap-3 group">
              Explore Features <ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
            </a>
          </motion.div>
        </motion.div>

        <div className="relative">
          <SoulCore />
          <TerminalPreview />
        </div>
      </div>
    </header>
  );
};
