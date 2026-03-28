import {AnimatePresence, motion} from "motion/react";
import {Menu, Star, Tag, X} from "lucide-react";
import {useState} from "react";

import {GITHUB_REPOSITORY_URL, type RepoSnapshot} from "../hooks/useRepoSnapshot";
import {MagneticButton, MagneticLink} from "./sitePrimitives";

type NavBarProps = {
  repoSnapshot: RepoSnapshot;
};

export const NavBar = ({repoSnapshot}: NavBarProps) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const navItems = [
    {label: "GitHub", href: GITHUB_REPOSITORY_URL},
    {label: "Docs", href: `${GITHUB_REPOSITORY_URL}/tree/main/docs`},
    {label: "Releases", href: repoSnapshot.releaseUrl},
  ];

  return (
    <>
      <nav className="fixed top-0 w-full z-50 bg-bg/50 backdrop-blur-xl border-b border-white/5">
        <div className="max-w-7xl mx-auto px-8 h-20 flex items-center justify-between">
          <motion.div initial={{opacity: 0, x: -20}} animate={{opacity: 1, x: 0}} className="flex items-center gap-3 group cursor-pointer">
            <div className="logo-badge group-hover:rotate-12 transition-transform">
              <img src="/logo.png" alt="SOUL logo" className="logo-image-header" />
            </div>
            <span className="font-black tracking-tighter text-2xl">SOUL</span>
          </motion.div>

          <div className="hidden md:flex items-center gap-6">
            <div className="flex items-center gap-10 text-sm font-bold text-text-muted uppercase tracking-widest">
              {navItems.map((item) => (
                <MagneticLink key={item.label} href={item.href} className="hover:text-accent transition-colors relative group">
                  {item.label}
                  <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-accent transition-all group-hover:w-full" />
                </MagneticLink>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <MagneticLink href={`${GITHUB_REPOSITORY_URL}/stargazers`} className="repo-header-pill">
                <Star className="w-3.5 h-3.5" />
                <span>{repoSnapshot.stars}</span>
              </MagneticLink>
              <MagneticLink href={repoSnapshot.releaseUrl} className="repo-header-pill">
                <Tag className="w-3.5 h-3.5" />
                <span>{repoSnapshot.version}</span>
              </MagneticLink>
            </div>
            <MagneticButton href={GITHUB_REPOSITORY_URL} className="btn-primary py-3 px-6 text-xs">
              Initialize
            </MagneticButton>
          </div>

          <button
            type="button"
            aria-label={isMobileMenuOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={isMobileMenuOpen}
            onClick={() => setIsMobileMenuOpen((value) => !value)}
            className="md:hidden mobile-menu-button"
          >
            {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
      </nav>

      <AnimatePresence>
        {isMobileMenuOpen ? (
          <motion.div
            initial={{opacity: 0, y: -12}}
            animate={{opacity: 1, y: 0}}
            exit={{opacity: 0, y: -12}}
            transition={{duration: 0.22, ease: "easeOut"}}
            className="fixed top-20 inset-x-0 z-40 px-4 md:hidden"
          >
            <div className="mobile-menu-panel">
              <div className="space-y-2">
                {navItems.map((item) => (
                  <a key={item.label} href={item.href} onClick={() => setIsMobileMenuOpen(false)} className="mobile-menu-link">
                    {item.label}
                  </a>
                ))}
              </div>

              <div className="flex flex-wrap gap-3 mt-5">
                <a href={`${GITHUB_REPOSITORY_URL}/stargazers`} onClick={() => setIsMobileMenuOpen(false)} className="repo-header-pill">
                  <Star className="w-3.5 h-3.5" />
                  <span>{repoSnapshot.stars}</span>
                </a>
                <a href={repoSnapshot.releaseUrl} onClick={() => setIsMobileMenuOpen(false)} className="repo-header-pill">
                  <Tag className="w-3.5 h-3.5" />
                  <span>{repoSnapshot.version}</span>
                </a>
              </div>

              <a href={GITHUB_REPOSITORY_URL} onClick={() => setIsMobileMenuOpen(false)} className="btn-primary mobile-menu-cta">
                Initialize
              </a>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
};
