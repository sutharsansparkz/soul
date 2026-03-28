import {startTransition, useEffect, useState} from "react";

export const GITHUB_REPOSITORY = "sparkz-technology/soul";
export const GITHUB_REPOSITORY_URL = `https://github.com/${GITHUB_REPOSITORY}`;
const GITHUB_REPOSITORY_API_URL = `https://api.github.com/repos/${GITHUB_REPOSITORY}`;

type GitHubRepoResponse = {
  stargazers_count?: number;
};

type GitHubReleaseResponse = {
  tag_name?: string;
  html_url?: string;
};

type GitHubContributorResponse = Array<{
  login?: string;
}>;

export type RepoSnapshot = {
  version: string;
  releaseUrl: string;
  stars: string;
  contributorCount: string;
  contributorNames: string[];
};

const FALLBACK_REPO_SNAPSHOT: RepoSnapshot = {
  version: "latest",
  releaseUrl: `${GITHUB_REPOSITORY_URL}/releases`,
  stars: "GitHub",
  contributorCount: "Open",
  contributorNames: ["GitHub community"],
};

const formatCompactNumber = (value: number | null | undefined) => {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "n/a";
  }

  return new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
};

const loadGitHubJson = async <T,>(url: string, signal: AbortSignal): Promise<T | null> => {
  const response = await fetch(url, {
    headers: {Accept: "application/vnd.github+json"},
    signal,
  });

  if (!response.ok) {
    return null;
  }

  return response.json() as Promise<T>;
};

export const useRepoSnapshot = () => {
  const [repoSnapshot, setRepoSnapshot] = useState(FALLBACK_REPO_SNAPSHOT);

  useEffect(() => {
    const controller = new AbortController();

    const loadRepoSnapshot = async () => {
      try {
        const [repoData, releaseData, contributorData] = await Promise.all([
          loadGitHubJson<GitHubRepoResponse>(GITHUB_REPOSITORY_API_URL, controller.signal),
          loadGitHubJson<GitHubReleaseResponse>(`${GITHUB_REPOSITORY_API_URL}/releases/latest`, controller.signal),
          loadGitHubJson<GitHubContributorResponse>(`${GITHUB_REPOSITORY_API_URL}/contributors?per_page=100&anon=1`, controller.signal),
        ]);

        if (controller.signal.aborted) {
          return;
        }

        const contributorNames =
          contributorData?.map((contributor) => contributor.login).filter((login): login is string => Boolean(login)).slice(0, 4) ?? [];

        startTransition(() => {
          setRepoSnapshot({
            version: releaseData?.tag_name ?? FALLBACK_REPO_SNAPSHOT.version,
            releaseUrl: releaseData?.html_url ?? FALLBACK_REPO_SNAPSHOT.releaseUrl,
            stars: repoData ? formatCompactNumber(repoData.stargazers_count) : FALLBACK_REPO_SNAPSHOT.stars,
            contributorCount:
              contributorData && contributorData.length > 0
                ? `${contributorData.length}+`
                : FALLBACK_REPO_SNAPSHOT.contributorCount,
            contributorNames: contributorNames.length > 0 ? contributorNames : FALLBACK_REPO_SNAPSHOT.contributorNames,
          });
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
      }
    };

    void loadRepoSnapshot();

    return () => controller.abort();
  }, []);

  return repoSnapshot;
};
