import {Canvas, useFrame} from "@react-three/fiber";
import {Float, MeshDistortMaterial, Sphere} from "@react-three/drei";
import {AnimatePresence, motion, useMotionValue, useSpring} from "motion/react";
import {Command, Terminal} from "lucide-react";
import {Suspense, useEffect, useRef, useState} from "react";
import * as THREE from "three";

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

export const CustomCursor = () => {
  const cursorX = useMotionValue(-100);
  const cursorY = useMotionValue(-100);
  const cursorXSpring = useSpring(cursorX, {damping: 25, stiffness: 700});
  const cursorYSpring = useSpring(cursorY, {damping: 25, stiffness: 700});

  useEffect(() => {
    const moveCursor = (e: MouseEvent) => {
      cursorX.set(e.clientX);
      cursorY.set(e.clientY);
    };

    window.addEventListener("mousemove", moveCursor);
    return () => window.removeEventListener("mousemove", moveCursor);
  }, [cursorX, cursorY]);

  return (
    <>
      <motion.div
        className="fixed top-0 left-0 w-8 h-8 border border-accent rounded-full pointer-events-none z-[999] mix-blend-difference"
        style={{x: cursorXSpring, y: cursorYSpring, translateX: "-50%", translateY: "-50%"}}
      />
      <motion.div
        className="fixed top-0 left-0 w-1.5 h-1.5 bg-accent rounded-full pointer-events-none z-[999]"
        style={{x: cursorX, y: cursorY, translateX: "-50%", translateY: "-50%"}}
      />
    </>
  );
};

export const SoulCore = () => {
  return (
    <div className="absolute inset-0 -z-10 overflow-hidden scale-110 lg:scale-150">
      <Canvas camera={{position: [0, 0, 5], fov: 45}}>
        <ambientLight intensity={0.5} />
        <spotLight position={[10, 10, 10]} angle={0.15} penumbra={1} intensity={2} color="#FF6321" />
        <pointLight position={[-10, -10, -10]} intensity={1} color="#3b82f6" />
        <Suspense fallback={null}>
          <AnimatedSphere />
          <Float speed={4} rotationIntensity={2} floatIntensity={1}>
            <Sphere args={[2.2, 32, 32]}>
              <meshStandardMaterial color="#FF6321" wireframe transparent opacity={0.1} />
            </Sphere>
          </Float>
        </Suspense>
      </Canvas>
    </div>
  );
};

export const TerminalPreview = () => {
  const [lines, setLines] = useState<string[]>([]);
  const fullLines = [
    "$ soul chat",
    "Ara - session 6ac1d0a1 - /quit to exit",
    "You: I had a rough day.",
    "Ara > Tell me the shape of it.",
    "[mood: warm] [context: venting] [history: 8]",
  ];

  useEffect(() => {
    let currentLine = 0;
    const interval = setInterval(() => {
      if (currentLine < fullLines.length) {
        setLines((prev) => [...prev, fullLines[currentLine]]);
        currentLine += 1;
        return;
      }
      clearInterval(interval);
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div
      initial={{opacity: 0, rotateY: 20, rotateX: 10}}
      animate={{opacity: 1, rotateY: 0, rotateX: 0}}
      transition={{duration: 1.2, ease: "easeOut"}}
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
              initial={{opacity: 0, x: -10}}
              animate={{opacity: 1, x: 0}}
              className={`mb-3 ${i === 0 ? "text-accent" : i === 3 ? "text-white font-bold" : i === 4 ? "text-accent/50 text-xs mt-4 pt-4 border-t border-white/5" : "text-text-muted"}`}
            >
              {line}
            </motion.div>
          ))}
        </AnimatePresence>
        <motion.div animate={{opacity: [1, 0]}} transition={{duration: 0.8, repeat: Infinity}} className="inline-block w-2 h-5 bg-accent ml-1 align-middle" />
      </div>
    </motion.div>
  );
};
