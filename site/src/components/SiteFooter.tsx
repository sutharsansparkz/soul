import {Users} from "lucide-react";

import {GITHUB_REPOSITORY_URL, type RepoSnapshot} from "../hooks/useRepoSnapshot";
import {MagneticLink} from "./sitePrimitives";

export const SiteFooter = ({repoSnapshot}: {repoSnapshot: RepoSnapshot}) => {
  return (
    <footer className="py-20 px-8 border-t border-white/5 bg-black">
      <div className="max-w-7xl mx-auto grid md:grid-cols-3 gap-16 items-center">
        <div className="flex items-center gap-4">
          <div className="logo-badge w-12 h-12 rounded-2xl">
            <img src="/logo.png" alt="SOUL logo" className="logo-image-footer" />
          </div>
          <span className="font-black tracking-tighter text-3xl">SOUL</span>
        </div>

        <div className="text-center text-text-muted text-sm font-medium">
          <div>© 2026 SOUL Project. Built for the terminal-native generation.</div>
          <MagneticLink href={`${GITHUB_REPOSITORY_URL}/graphs/contributors`} className="repo-footer-link">
            <Users className="w-3.5 h-3.5" />
            <span>Contributors {repoSnapshot.contributorCount}:</span>
            <span>{repoSnapshot.contributorNames.join(", ")}</span>
          </MagneticLink>
        </div>

        <div className="flex justify-center md:justify-end gap-8 text-sm font-black uppercase tracking-widest text-text-muted">
          <MagneticLink href={GITHUB_REPOSITORY_URL} className="hover:text-accent transition-colors">Github</MagneticLink>
          <MagneticLink href={`${GITHUB_REPOSITORY_URL}/issues`} className="hover:text-accent transition-colors">Issues</MagneticLink>
        </div>
      </div>
    </footer>
  );
};
