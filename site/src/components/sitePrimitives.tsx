import {motion, useMotionValue, useSpring} from "motion/react";
import type {MouseEvent as ReactMouseEvent, ReactNode} from "react";
import {useRef} from "react";

export const FloatingParticles = () => {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none -z-10">
      {[...Array(20)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute w-1 h-1 bg-accent/20 rounded-full"
          initial={{
            x: Math.random() * 100 + "%",
            y: Math.random() * 100 + "%",
            opacity: Math.random() * 0.5,
          }}
          animate={{
            y: [null, Math.random() * -100 + "%"],
            opacity: [0, 0.5, 0],
          }}
          transition={{
            duration: Math.random() * 10 + 10,
            repeat: Infinity,
            ease: "linear",
          }}
        />
      ))}
    </div>
  );
};

type MagneticAnchorProps = {
  children: ReactNode;
  className?: string;
  href: string;
};

const MagneticAnchor = ({children, className, href}: MagneticAnchorProps) => {
  const ref = useRef<HTMLAnchorElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const dx = useSpring(x, {damping: 15, stiffness: 150});
  const dy = useSpring(y, {damping: 15, stiffness: 150});

  const handleMouseMove = (e: ReactMouseEvent) => {
    if (!ref.current) return;
    const {clientX, clientY} = e;
    const {left, top, width, height} = ref.current.getBoundingClientRect();
    const centerX = left + width / 2;
    const centerY = top + height / 2;
    x.set((clientX - centerX) * 0.35);
    y.set((clientY - centerY) * 0.35);
  };

  return (
    <motion.a
      ref={ref}
      href={href}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => {
        x.set(0);
        y.set(0);
      }}
      style={{x: dx, y: dy}}
      className={className}
    >
      {children}
    </motion.a>
  );
};

export const MagneticButton = (props: MagneticAnchorProps) => <MagneticAnchor {...props} />;

export const MagneticLink = (props: MagneticAnchorProps) => <MagneticAnchor {...props} />;

export const RevealOnScroll = ({children, delay = 0}: {children: ReactNode; delay?: number}) => {
  return (
    <motion.div
      initial={{opacity: 0, y: 50}}
      whileInView={{opacity: 1, y: 0}}
      viewport={{once: true, margin: "-100px"}}
      transition={{duration: 0.8, delay, ease: [0.215, 0.61, 0.355, 1]}}
    >
      {children}
    </motion.div>
  );
};

export const TextReveal = ({text, className}: {text: string; className?: string}) => {
  const words = text.split(" ");

  return (
    <div className={className}>
      {words.map((word, i) => (
        <span key={i} className="inline-block overflow-hidden mr-[0.2em] pb-[0.1em]">
          <motion.span
            initial={{y: "100%"}}
            animate={{y: 0}}
            transition={{duration: 0.8, delay: i * 0.1, ease: [0.215, 0.61, 0.355, 1]}}
            className="inline-block"
          >
            {word}
          </motion.span>
        </span>
      ))}
    </div>
  );
};
