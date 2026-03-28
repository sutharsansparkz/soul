import {motion, useScroll, useTransform} from "motion/react";
import {useRef} from "react";

import {GITHUB_REPOSITORY_URL} from "../hooks/useRepoSnapshot";
import {MagneticButton, RevealOnScroll} from "./sitePrimitives";

export const ParallaxCTA = () => {
  const sectionRef = useRef<HTMLElement>(null);
  const {scrollYProgress} = useScroll({target: sectionRef, offset: ["start end", "end start"]});
  const x = useTransform(scrollYProgress, [0, 1], [200, -200]);
  const y = useTransform(scrollYProgress, [0, 1], [-100, 100]);
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [0.8, 1, 0.8]);

  return (
    <section ref={sectionRef} className="py-48 px-8 bg-accent overflow-hidden relative">
      <motion.div style={{x, opacity: 0.1}} className="absolute top-1/2 left-0 -translate-y-1/2 text-[25vw] font-black text-black whitespace-nowrap pointer-events-none select-none">
        TERMINAL FIRST TERMINAL FIRST TERMINAL FIRST
      </motion.div>

      <motion.div style={{y, scale}} className="max-w-7xl mx-auto relative z-10 text-center">
        <RevealOnScroll>
          <h2 className="text-7xl lg:text-9xl font-black text-black tracking-tighter mb-12 leading-none">
            READY TO <br /> INITIALIZE?
          </h2>
          <MagneticButton href={GITHUB_REPOSITORY_URL} className="bg-black text-white px-16 py-8 rounded-full font-black text-2xl hover:scale-110 transition-transform inline-block shadow-2xl">
            GET STARTED NOW
          </MagneticButton>
        </RevealOnScroll>
      </motion.div>

      <motion.div style={{rotate: 45, x: useTransform(scrollYProgress, [0, 1], [-100, 100])}} className="absolute top-20 left-20 w-32 h-32 border-4 border-black/20 rounded-3xl" />
      <motion.div style={{rotate: -45, x: useTransform(scrollYProgress, [0, 1], [100, -100])}} className="absolute bottom-20 right-20 w-48 h-48 border-4 border-black/20 rounded-full" />
    </section>
  );
};
