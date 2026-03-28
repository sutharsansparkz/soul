import {motion, useMotionValue, useTransform} from "motion/react";
import {Brain, Cpu, Database, Zap} from "lucide-react";
import type {MouseEvent as ReactMouseEvent} from "react";

import {RevealOnScroll} from "./sitePrimitives";

const FeatureCard = ({
  icon: Icon,
  title,
  description,
  index,
}: {
  icon: any;
  title: string;
  description: string;
  index: number;
}) => {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotateX = useTransform(y, [-100, 100], [10, -10]);
  const rotateY = useTransform(x, [-100, 100], [-10, 10]);

  const handleMouseMove = (e: ReactMouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const centerX = rect.left + rect.width / 2;
    const centerY = rect.top + rect.height / 2;
    x.set(e.clientX - centerX);
    y.set(e.clientY - centerY);
  };

  return (
    <motion.div
      initial={{opacity: 0, y: 30}}
      whileInView={{opacity: 1, y: 0}}
      viewport={{once: true}}
      transition={{delay: index * 0.1, duration: 0.5}}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => {
        x.set(0);
        y.set(0);
      }}
      style={{rotateX, rotateY, perspective: 1000}}
      className="glass-card p-8 group relative overflow-hidden cursor-none"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-accent/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      <div className="w-14 h-14 rounded-2xl bg-accent-muted flex items-center justify-center mb-6 group-hover:bg-accent group-hover:text-white transition-all duration-300 group-hover:scale-110 group-hover:rotate-6">
        <Icon className="w-7 h-7" />
      </div>
      <h3 className="text-xl font-bold mb-3 group-hover:text-accent transition-colors tracking-tight">{title}</h3>
      <p className="text-text-muted leading-relaxed group-hover:text-white/80 transition-colors text-sm">{description}</p>
      <div className="absolute top-0 right-0 w-12 h-12 bg-accent/5 -mr-6 -mt-6 rotate-45 group-hover:bg-accent/20 transition-colors" />
    </motion.div>
  );
};

export const FeaturesSection = () => {
  const stats = [
    {label: "Memory", value: "SQLite"},
    {label: "Interface", value: "Terminal"},
    {label: "Personality", value: "Dynamic"},
    {label: "Privacy", value: "Local-First"},
  ];
  const features = [
    {icon: Database, title: "Persistent Memory", description: "Every session, fact, and reflection is stored locally in SQLite for long-term recall."},
    {icon: Brain, title: "Mood-Aware", description: "Mood classification shapes each turn before the LLM generates a response."},
    {icon: Zap, title: "Personality Drift", description: "Resonance signals gradually nudge humor, warmth, and curiosity over time."},
    {icon: Cpu, title: "Maintenance Jobs", description: "Automated consolidation, decay, and proactive follow-up jobs on local state."},
  ];

  return (
    <>
      <section className="py-20 border-y border-white/5 bg-white/[0.02]">
        <div className="max-w-7xl mx-auto px-8 grid grid-cols-2 md:grid-cols-4 gap-12">
          {stats.map((stat, i) => (
            <RevealOnScroll key={stat.label} delay={i * 0.1}>
              <div className="text-center group">
                <div className="text-3xl font-black text-white mb-2 group-hover:text-accent transition-colors">{stat.value}</div>
                <div className="text-xs font-bold uppercase tracking-widest text-accent/60 group-hover:text-accent transition-colors">{stat.label}</div>
              </div>
            </RevealOnScroll>
          ))}
        </div>
      </section>

      <section id="features" className="py-32 px-8 relative">
        <div className="max-w-7xl mx-auto">
          <div className="mb-20">
            <RevealOnScroll>
              <h2 className="text-sm font-black uppercase tracking-[0.4em] text-accent mb-6">Core Engine</h2>
            </RevealOnScroll>
            <RevealOnScroll delay={0.2}>
              <p className="text-5xl lg:text-6xl font-black tracking-tighter max-w-3xl">Built for continuity, not disposable chat.</p>
            </RevealOnScroll>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            {features.map((feature, index) => (
              <FeatureCard key={feature.title} index={index} {...feature} />
            ))}
          </div>
        </div>
      </section>
    </>
  );
};
