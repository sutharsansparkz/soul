/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { motion, useScroll, useTransform, useSpring, useMotionValue, AnimatePresence } from "motion/react";
import React, { useState, useEffect, useRef, ReactNode, MouseEvent as ReactMouseEvent, Suspense } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshDistortMaterial, Sphere, MeshWobbleMaterial } from "@react-three/drei";
import * as THREE from "three";
import { 
  Github, 
  Terminal, 
  Database, 
  Brain, 
  Cpu, 
  MessageSquare, 
  Mic, 
  ArrowRight, 
  BookOpen, 
  Activity,
  Zap,
  Sparkles,
  Command
} from "lucide-react";

// --- Advanced Components ---

const FloatingParticles = () => {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none -z-10">
      {[...Array(20)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-1 h-1 bg-accent/20 rounded-full"
          initial={{ 
            x: Math.random() * 100 + "%", 
            y: Math.random() * 100 + "%",
            opacity: Math.random() * 0.5
          }}
          animate={{
            y: [null, Math.random() * -100 + "%"],
            opacity: [0, 0.5, 0]
          }}
          transition={{
            duration: Math.random() * 10 + 10,
            repeat: Infinity,
            ease: "linear"
          }}
        />
      ))}
    </div>
  );
};

const MagneticButton = ({ children, className, href }: { children: ReactNode, className: string, href: string }) => {
  const ref = useRef<HTMLAnchorElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const springConfig = { damping: 15, stiffness: 150 };
  const dx = useSpring(x, springConfig);
  const dy = useSpring(y, springConfig);

  const handleMouseMove = (e: ReactMouseEvent) => {
    if (!ref.current) return;
    const { clientX, clientY } = e;
    const { left, top, width, height } = ref.current.getBoundingClientRect();
    const centerX = left + width / 2;
    const centerY = top + height / 2;
    x.set((clientX - centerX) * 0.3);
    y.set((clientY - centerY) * 0.3);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.a
      ref={ref}
      href={href}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ x: dx, y: dy }}
      className={className}
    >
      {children}
    </motion.a>
  );
};

const CustomCursor = () => {
  const cursorX = useMotionValue(-100);
  const cursorY = useMotionValue(-100);
  const springConfig = { damping: 25, stiffness: 700 };
  const cursorXSpring = useSpring(cursorX, springConfig);
  const cursorYSpring = useSpring(cursorY, springConfig);

  useEffect(() => {
    const moveCursor = (e: MouseEvent) => {
      cursorX.set(e.clientX);
      cursorY.set(e.clientY);
    };
    window.addEventListener("mousemove", moveCursor);
    return () => window.removeEventListener("mousemove", moveCursor);
  }, []);

  return (
    <>
      <motion.div
        className="fixed top-0 left-0 w-8 h-8 border border-accent rounded-full pointer-events-none z-[999] mix-blend-difference"
        style={{
          x: cursorXSpring,
          y: cursorYSpring,
          translateX: "-50%",
          translateY: "-50%",
        }}
      />
      <motion.div
        className="fixed top-0 left-0 w-1.5 h-1.5 bg-accent rounded-full pointer-events-none z-[999]"
        style={{
          x: cursorX,
          y: cursorY,
          translateX: "-50%",
          translateY: "-50%",
        }}
      />
    </>
  );
};

const FeatureCard = ({ icon: Icon, title, description, index }: { icon: any, title: string, description: string, index: number }) => {
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

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.1, duration: 0.5 }}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ rotateX, rotateY, perspective: 1000 }}
      className="glass-card p-8 group relative overflow-hidden cursor-none"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-accent/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
      <div className="w-14 h-14 rounded-2xl bg-accent-muted flex items-center justify-center mb-6 group-hover:bg-accent group-hover:text-white transition-all duration-300 group-hover:scale-110 group-hover:rotate-6">
        <Icon className="w-7 h-7" />
      </div>
      <h3 className="text-xl font-bold mb-3 group-hover:text-accent transition-colors tracking-tight">{title}</h3>
      <p className="text-text-muted leading-relaxed group-hover:text-white/80 transition-colors text-sm">{description}</p>
      
      {/* Decorative corner */}
      <div className="absolute top-0 right-0 w-12 h-12 bg-accent/5 -mr-6 -mt-6 rotate-45 group-hover:bg-accent/20 transition-colors" />
    </motion.div>
  );
};

const RevealOnScroll = ({ children, delay = 0 }: { children: ReactNode, delay?: number, key?: any }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 50 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-100px" }}
      transition={{ duration: 0.8, delay, ease: [0.215, 0.61, 0.355, 1] }}
    >
      {children}
    </motion.div>
  );
};

const MagneticLink = ({ children, href, className }: { children: ReactNode, href: string, className?: string, key?: any }) => {
  const ref = useRef<HTMLAnchorElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const springConfig = { damping: 15, stiffness: 150 };
  const dx = useSpring(x, springConfig);
  const dy = useSpring(y, springConfig);

  const handleMouseMove = (e: ReactMouseEvent) => {
    if (!ref.current) return;
    const { clientX, clientY } = e;
    const { left, top, width, height } = ref.current.getBoundingClientRect();
    const centerX = left + width / 2;
    const centerY = top + height / 2;
    x.set((clientX - centerX) * 0.5);
    y.set((clientY - centerY) * 0.5);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <motion.a
      ref={ref}
      href={href}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={{ x: dx, y: dy }}
      className={className}
    >
      {children}
    </motion.a>
  );
};

const TextReveal = ({ text, className }: { text: string, className?: string }) => {
  const words = text.split(" ");
  
  return (
    <div className={className}>
      {words.map((word, i) => (
        <span key={i} className="inline-block overflow-hidden mr-[0.2em] pb-[0.1em]">
          <motion.span
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            transition={{ 
              duration: 0.8, 
              delay: i * 0.1, 
              ease: [0.215, 0.61, 0.355, 1] 
            }}
            className="inline-block"
          >
            {word}
          </motion.span>
        </span>
      ))}
    </div>
  );
};

const AnimatedSphere = () => {
  const meshRef = useRef<THREE.Mesh>(null);
  
  useFrame((state) => {
    if (!meshRef.current) return;
    meshRef.current.rotation.x = state.clock.getElapsedTime() * 0.3;
    meshRef.current.rotation.y = state.clock.getElapsedTime() * 0.2;
  });

  return (
    <Float speed={2} rotationIntensity={1} floatIntensity={2}>
      <Sphere ref={meshRef} args={[1.6, 128, 128]}>
        <MeshDistortMaterial
          color="#FF6321"
          attach="material"
          distort={0.5}
          speed={3}
          roughness={0}
          metalness={1}
          emissive="#FF6321"
          emissiveIntensity={0.3}
        />
      </Sphere>
    </Float>
  );
};

const SoulCore = () => {
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden scale-110 lg:scale-150">
      <Canvas camera={{ position: [0, 0, 5], fov: 45 }}>
        <ambientLight intensity={0.5} />
        <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} intensity={2} color="#FF6321" />
        <pointLight position={[-10, -10, -10]} intensity={1} color="#3b82f6" />
        
        <Suspense fallback={null}>
          <AnimatedSphere />
          
          <Float speed={4} rotationIntensity={2} floatIntensity={1}>
            <Sphere args={[2.2, 32, 32]}>
              <meshStandardMaterial
                color="#FF6321"
                wireframe
                transparent
                opacity={0.1}
              />
            </Sphere>
          </Float>
        </Suspense>
      </Canvas>
    </div>
  );
};

const TerminalPreview = () => {
  const [lines, setLines] = useState<string[]>([]);
  const fullLines = [
    "$ soul chat",
    "Ara - session 6ac1d0a1 - /quit to exit",
    "You: I had a rough day.",
    "Ara > Tell me the shape of it.",
    "[mood: warm] [context: venting] [history: 8]"
  ];

  useEffect(() => {
    let currentLine = 0;
    const interval = setInterval(() => {
      if (currentLine < fullLines.length) {
        setLines(prev => [...prev, fullLines[currentLine]]);
        currentLine++;
      } else {
        clearInterval(interval);
      }
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div 
      initial={{ opacity: 0, rotateY: 20, rotateX: 10 }}
      animate={{ opacity: 1, rotateY: 0, rotateX: 0 }}
      transition={{ duration: 1.2, ease: "easeOut" }}
      className="terminal-window group"
    >
      <div className="bg-surface px-4 py-3 border-b border-white/5 flex items-center justify-between">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/40" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/40" />
          <div className="w-3 h-3 rounded-full bg-green-500/40" />
        </div>
        <div className="text-[10px] font-mono text-text-muted uppercase tracking-widest flex items-center gap-2">
          <Command className="w-3 h-3" /> soul.exe
        </div>
      </div>
      <div className="p-8 font-mono text-sm leading-relaxed min-h-[300px] relative">
        <div className="scanline" />
        <AnimatePresence>
          {lines.map((line, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              className={`mb-3 ${i === 0 ? 'text-accent' : i === 3 ? 'text-white font-bold' : i === 4 ? 'text-accent/50 text-xs mt-4 pt-4 border-t border-white/5' : 'text-text-muted'}`}
            >
              {line}
            </motion.div>
          ))}
        </AnimatePresence>
        <motion.div 
          animate={{ opacity: [1, 0] }} 
          transition={{ duration: 0.8, repeat: Infinity }}
          className="inline-block w-2 h-5 bg-accent ml-1 align-middle"
        />
      </div>
    </motion.div>
  );
};

const ParallaxCTA = () => {
  const sectionRef = useRef(null);
  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start end", "end start"]
  });

  const x = useTransform(scrollYProgress, [0, 1], [200, -200]);
  const y = useTransform(scrollYProgress, [0, 1], [-100, 100]);
  const scale = useTransform(scrollYProgress, [0, 0.5, 1], [0.8, 1, 0.8]);

  return (
    <section ref={sectionRef} className="py-48 px-8 bg-accent overflow-hidden relative">
      <motion.div 
        style={{ x, opacity: 0.1 }}
        className="absolute top-1/2 left-0 -translate-y-1/2 text-[25vw] font-black text-black whitespace-nowrap pointer-events-none select-none"
      >
        TERMINAL FIRST TERMINAL FIRST TERMINAL FIRST
      </motion.div>
      
      <motion.div 
        style={{ y, scale }}
        className="max-w-7xl mx-auto relative z-10 text-center"
      >
        <RevealOnScroll>
          <h2 className="text-7xl lg:text-9xl font-black text-black tracking-tighter mb-12 leading-none">
            READY TO <br /> INITIALIZE?
          </h2>
          <MagneticButton href="https://github.com/sparkz-technology/soul" className="bg-black text-white px-16 py-8 rounded-full font-black text-2xl hover:scale-110 transition-transform inline-block shadow-2xl">
            GET STARTED NOW
          </MagneticButton>
        </RevealOnScroll>
      </motion.div>

      {/* Decorative elements */}
      <motion.div 
        style={{ rotate: 45, x: useTransform(scrollYProgress, [0, 1], [-100, 100]) }}
        className="absolute top-20 left-20 w-32 h-32 border-4 border-black/20 rounded-3xl"
      />
      <motion.div 
        style={{ rotate: -45, x: useTransform(scrollYProgress, [0, 1], [100, -100]) }}
        className="absolute bottom-20 right-20 w-48 h-48 border-4 border-black/20 rounded-full"
      />
    </section>
  );
};

export default function App() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 100, damping: 30, restDelta: 0.001 });
  
  const heroRef = useRef(null);
  const { scrollY } = useScroll();
  const y1 = useTransform(scrollY, [0, 500], [0, 200]);
  const opacity = useTransform(scrollY, [0, 300], [1, 0]);

  return (
    <div className="min-h-screen relative cursor-none">
      <CustomCursor />
      <div className="grain" />
      <FloatingParticles />
      
      {/* Progress Bar */}
      <motion.div className="fixed top-0 left-0 right-0 h-1 bg-accent z-[100] origin-left" style={{ scaleX }} />

      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 bg-bg/50 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-7xl mx-auto px-8 h-20 flex items-center justify-between">
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex items-center gap-3 group cursor-pointer"
          >
            <div className="w-10 h-10 bg-accent rounded-xl flex items-center justify-center group-hover:rotate-12 transition-transform">
              <Terminal className="text-white w-6 h-6" />
            </div>
            <span className="font-black tracking-tighter text-2xl">SOUL</span>
          </motion.div>
          
          <div className="hidden md:flex items-center gap-10 text-sm font-bold text-text-muted uppercase tracking-widest">
            {["GitHub", "Docs", "Releases"].map((item, i) => (
              <MagneticLink 
                key={item}
                href={`https://github.com/sparkz-technology/soul${item === 'GitHub' ? '' : item === 'Docs' ? '/tree/main/docs' : '/releases'}`} 
                className="hover:text-accent transition-colors relative group"
              >
                {item}
                <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-accent transition-all group-hover:w-full" />
              </MagneticLink>
            ))}
            <MagneticButton href="https://github.com/sparkz-technology/soul" className="btn-primary py-3 px-6 text-xs">
              Initialize
            </MagneticButton>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <header ref={heroRef} className="relative pt-48 pb-32 px-8 overflow-hidden">
        <div className="max-w-7xl mx-auto grid lg:grid-cols-2 gap-20 items-center">
          <motion.div style={{ y: y1, opacity }}>
            <motion.div 
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
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
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.6 }}
              className="text-xl text-text-muted leading-relaxed mb-12 max-w-xl font-medium"
            >
              SOUL is a persistent companion that lives in your terminal. It remembers your past, adapts to your mood, and evolves over time.
            </motion.p>
            
            <motion.div 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.8 }}
              className="flex flex-wrap gap-6"
            >
              <MagneticButton href="https://github.com/sparkz-technology/soul" className="btn-primary flex items-center gap-3">
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

      {/* Stats Section */}
      <section className="py-20 border-y border-white/5 bg-white/[0.02]">
        <div className="max-w-7xl mx-auto px-8 grid grid-cols-2 md:grid-cols-4 gap-12">
          {[
            { label: "Memory", value: "SQLite" },
            { label: "Interface", value: "Terminal" },
            { label: "Personality", value: "Dynamic" },
            { label: "Privacy", value: "Local-First" }
          ].map((stat, i) => (
            <RevealOnScroll key={i} delay={i * 0.1}>
              <div className="text-center group">
                <div className="text-3xl font-black text-white mb-2 group-hover:text-accent transition-colors">{stat.value}</div>
                <div className="text-xs font-bold uppercase tracking-widest text-accent/60 group-hover:text-accent transition-colors">{stat.label}</div>
              </div>
            </RevealOnScroll>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="py-32 px-8 relative">
        <div className="max-w-7xl mx-auto">
          <div className="mb-20">
            <RevealOnScroll>
              <h2 className="text-sm font-black uppercase tracking-[0.4em] text-accent mb-6">
                Core Engine
              </h2>
            </RevealOnScroll>
            <RevealOnScroll delay={0.2}>
              <p className="text-5xl lg:text-6xl font-black tracking-tighter max-w-3xl">
                Built for continuity, not disposable chat.
              </p>
            </RevealOnScroll>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <FeatureCard 
              index={0}
              icon={Database}
              title="Persistent Memory"
              description="Every session, fact, and reflection is stored locally in SQLite for long-term recall."
            />
            <FeatureCard 
              index={1}
              icon={Brain}
              title="Mood-Aware"
              description="Mood classification shapes each turn before the LLM generates a response."
            />
            <FeatureCard 
              index={2}
              icon={Zap}
              title="Personality Drift"
              description="Resonance signals gradually nudge humor, warmth, and curiosity over time."
            />
            <FeatureCard 
              index={3}
              icon={Cpu}
              title="Maintenance Jobs"
              description="Automated consolidation, decay, and proactive follow-up jobs on local state."
            />
          </div>
        </div>
      </section>

      {/* Parallax Section */}
      <ParallaxCTA />

      {/* Footer */}
      <footer className="py-20 px-8 border-t border-white/5 bg-black">
        <div className="max-w-7xl mx-auto grid md:grid-cols-3 gap-16 items-center">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-accent rounded-2xl flex items-center justify-center">
              <Terminal className="text-white w-7 h-7" />
            </div>
            <span className="font-black tracking-tighter text-3xl">SOUL</span>
          </div>
          
          <div className="text-center text-text-muted text-sm font-medium">
            © 2026 SOUL Project. Built for the terminal-native generation.
          </div>
          
          <div className="flex justify-center md:justify-end gap-8 text-sm font-black uppercase tracking-widest text-text-muted">
            <MagneticLink href="https://github.com/sparkz-technology/soul" className="hover:text-accent transition-colors">Github</MagneticLink>
            <MagneticLink href="https://github.com/sparkz-technology/soul/issues" className="hover:text-accent transition-colors">Issues</MagneticLink>
          </div>
        </div>
      </footer>
    </div>
  );
}
