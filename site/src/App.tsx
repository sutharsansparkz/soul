import {motion, useScroll, useSpring} from "motion/react";

import {FeaturesSection} from "./components/FeaturesSection.tsx";
import {HeroSection} from "./components/HeroSection.tsx";
import {InstallSection} from "./components/InstallSection.tsx";
import {NavBar} from "./components/NavBar.tsx";
import {ParallaxCTA} from "./components/ParallaxCTA.tsx";
import {CustomCursor} from "./components/SiteScene.tsx";
import {SiteFooter} from "./components/SiteFooter.tsx";
import {FloatingParticles} from "./components/sitePrimitives.tsx";
import {useRepoSnapshot} from "./hooks/useRepoSnapshot.ts";

export default function App() {
  const {scrollYProgress} = useScroll();
  const scaleX = useSpring(scrollYProgress, {stiffness: 100, damping: 30, restDelta: 0.001});
  const repoSnapshot = useRepoSnapshot();

  return (
    <div className="min-h-screen relative cursor-none">
      <CustomCursor />
      <div className="grain" />
      <FloatingParticles />
      <motion.div className="fixed top-0 left-0 right-0 h-1 bg-accent z-[100] origin-left" style={{scaleX}} />
      <NavBar repoSnapshot={repoSnapshot} />
      <HeroSection />
      <InstallSection />
      <FeaturesSection />
      <ParallaxCTA />
      <SiteFooter repoSnapshot={repoSnapshot} />
    </div>
  );
}
