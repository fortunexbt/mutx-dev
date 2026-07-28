import packageJson from "../package.json";

export const MUTX_GITHUB_OWNER = "mutx-dev";
export const MUTX_GITHUB_REPO = "mutx-dev";
export const MUTX_GITHUB_RELEASES_URL = `https://github.com/${MUTX_GITHUB_OWNER}/${MUTX_GITHUB_REPO}/releases`;
export const MUTX_SITE_URL = "https://mutx.dev";
export const DESKTOP_RELEASE_REVALIDATE_SECONDS = 900;
export const DESKTOP_RELEASE_MAX_PAGES = 5;

const DESKTOP_RELEASES_PER_PAGE = 20;
const DESKTOP_CHECKSUM_MANIFEST_MAX_BYTES = 4096;
const MUTX_GITHUB_RELEASES_API_URL = `https://api.github.com/repos/${MUTX_GITHUB_OWNER}/${MUTX_GITHUB_REPO}/releases?per_page=${DESKTOP_RELEASES_PER_PAGE}`;

export type GitHubReleaseAsset = {
  name: string;
  browser_download_url: string;
  size: number;
  state: "uploaded";
};

export type GitHubRelease = {
  tag_name: string;
  draft: boolean;
  prerelease: boolean;
  html_url: string;
  assets: GitHubReleaseAsset[];
};

export type DesktopReleaseInfo = {
  tagName: string;
  version: string;
  htmlUrl: string;
  assets: {
    arm64Dmg: string;
    x64Dmg: string;
    arm64Zip: string;
    x64Zip: string;
    checksums: string;
  };
};

type DesktopAssetKind = "arm64-dmg" | "x64-dmg" | "arm64-zip" | "x64-zip" | "checksums";

const stableReleaseTagPattern = /^v(\d+)\.(\d+)\.(\d+)$/;
export const MUTX_RELEASE_NOTES_URL = buildReleaseNotesUrl(packageJson.version);

function getGitHubRequestHeaders(): HeadersInit {
  const headers: HeadersInit = {
    Accept: "application/vnd.github+json",
    "User-Agent": "mutx.dev-download-resolver",
    "X-GitHub-Api-Version": "2022-11-28",
  };

  const token = process.env.MUTX_GITHUB_RELEASES_TOKEN?.trim();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  return headers;
}

function parseStableReleaseVersion(tagName: string): [number, number, number] | null {
  const match = stableReleaseTagPattern.exec(tagName);
  if (!match) {
    return null;
  }

  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function compareSemver(left: [number, number, number], right: [number, number, number]) {
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return left[index] - right[index];
    }
  }

  return 0;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isExpectedGitHubReleaseUrl(urlString: string, tagName: string) {
  try {
    const url = new URL(urlString);
    return (
      url.origin === "https://github.com" &&
      url.pathname === `/${MUTX_GITHUB_OWNER}/${MUTX_GITHUB_REPO}/releases/tag/${tagName}`
    );
  } catch {
    return false;
  }
}

function isGitHubRelease(value: unknown): value is GitHubRelease {
  if (!isRecord(value)) {
    return false;
  }

  const { tag_name: tagName, draft, prerelease, html_url: htmlUrl, assets } = value;
  return (
    typeof tagName === "string" &&
    typeof draft === "boolean" &&
    typeof prerelease === "boolean" &&
    typeof htmlUrl === "string" &&
    isExpectedGitHubReleaseUrl(htmlUrl, tagName) &&
    Array.isArray(assets) &&
    assets.every(
      (asset) =>
        isRecord(asset) &&
        typeof asset.name === "string" &&
        typeof asset.browser_download_url === "string" &&
        typeof asset.size === "number" &&
        Number.isSafeInteger(asset.size) &&
        asset.size > 0 &&
        asset.state === "uploaded",
    )
  );
}

export function buildDesktopArtifactName(version: string, kind: DesktopAssetKind) {
  switch (kind) {
    case "arm64-dmg":
      return `MUTX-${version}-macos-arm64.dmg`;
    case "x64-dmg":
      return `MUTX-${version}-macos-x64.dmg`;
    case "arm64-zip":
      return `MUTX-${version}-macos-arm64.zip`;
    case "x64-zip":
      return `MUTX-${version}-macos-x64.zip`;
    case "checksums":
      return `MUTX-${version}-SHA256SUMS.txt`;
    default: {
      const exhaustiveCheck: never = kind;
      return exhaustiveCheck;
    }
  }
}

export function buildReleaseNotesUrl(version: string) {
  const [major, minor] = version.split(".");
  return `${MUTX_SITE_URL}/docs/releases/v${major}.${minor}`;
}

function getAssetUrl(release: GitHubRelease, assetName: string) {
  const assetUrl = release.assets.find(
    (asset) => asset.name === assetName,
  )?.browser_download_url;
  if (!assetUrl) {
    return null;
  }

  try {
    const url = new URL(assetUrl);
    const expectedPath = `/${MUTX_GITHUB_OWNER}/${MUTX_GITHUB_REPO}/releases/download/${release.tag_name}/${assetName}`;
    return url.origin === "https://github.com" && url.pathname === expectedPath ? assetUrl : null;
  } catch {
    return null;
  }
}

function getStableDesktopReleaseCandidates(releases: readonly unknown[]) {
  return releases
    .filter(isGitHubRelease)
    .map((release) => ({
      release,
      version: parseStableReleaseVersion(release.tag_name),
    }))
    .filter(
      (candidate): candidate is { release: GitHubRelease; version: [number, number, number] } =>
        !candidate.release.draft &&
        !candidate.release.prerelease &&
        candidate.version !== null &&
        normalizeDesktopRelease(candidate.release) !== null,
    )
    .sort((left, right) => compareSemver(right.version, left.version))
    .map((candidate) => candidate.release);
}

export function findLatestStableAppRelease(releases: readonly unknown[]) {
  return getStableDesktopReleaseCandidates(releases)[0] ?? null;
}

export function normalizeDesktopRelease(release: GitHubRelease): DesktopReleaseInfo | null {
  if (!isGitHubRelease(release)) {
    return null;
  }

  const versionParts = parseStableReleaseVersion(release.tag_name);
  if (!versionParts) {
    return null;
  }

  const version = versionParts.join(".");
  const expectedAssetNames = new Set<DesktopAssetKind>([
    "arm64-dmg",
    "x64-dmg",
    "arm64-zip",
    "x64-zip",
    "checksums",
  ]);
  const expectedNames = new Set(
    [...expectedAssetNames].map((kind) => buildDesktopArtifactName(version, kind)),
  );
  if (
    release.assets.length !== expectedNames.size ||
    release.assets.some((asset) => !expectedNames.has(asset.name))
  ) {
    return null;
  }

  const arm64Dmg = getAssetUrl(release, buildDesktopArtifactName(version, "arm64-dmg"));
  const x64Dmg = getAssetUrl(release, buildDesktopArtifactName(version, "x64-dmg"));
  const arm64Zip = getAssetUrl(release, buildDesktopArtifactName(version, "arm64-zip"));
  const x64Zip = getAssetUrl(release, buildDesktopArtifactName(version, "x64-zip"));
  const checksums = getAssetUrl(release, buildDesktopArtifactName(version, "checksums"));

  if (!arm64Dmg || !x64Dmg || !arm64Zip || !x64Zip || !checksums) {
    return null;
  }

  return {
    tagName: release.tag_name,
    version,
    htmlUrl: release.html_url,
    assets: {
      arm64Dmg,
      x64Dmg,
      arm64Zip,
      x64Zip,
      checksums,
    },
  };
}

export function isValidDesktopChecksumManifest(body: string, version: string) {
  if (body.length === 0 || body.length > DESKTOP_CHECKSUM_MANIFEST_MAX_BYTES || body.includes("\r")) {
    return false;
  }

  const expectedNames = new Set([
    buildDesktopArtifactName(version, "arm64-dmg"),
    buildDesktopArtifactName(version, "x64-dmg"),
    buildDesktopArtifactName(version, "arm64-zip"),
    buildDesktopArtifactName(version, "x64-zip"),
  ]);
  const lines = body.endsWith("\n") ? body.slice(0, -1).split("\n") : body.split("\n");
  const observedNames = new Set<string>();

  if (lines.length !== expectedNames.size) {
    return false;
  }

  for (const line of lines) {
    const match = /^[0-9a-f]{64} {2}([^/\s]+)$/.exec(line);
    const fileName = match?.[1];
    if (!fileName || !expectedNames.has(fileName) || observedNames.has(fileName)) {
      return false;
    }
    observedNames.add(fileName);
  }

  return observedNames.size === expectedNames.size;
}

async function hasValidDesktopChecksumManifest(
  release: DesktopReleaseInfo,
  fetchImpl: typeof fetch,
) {
  try {
    const response = await fetchImpl(release.assets.checksums, {
      headers: {
        Accept: "text/plain",
        "User-Agent": "mutx.dev-download-resolver",
      },
      next: { revalidate: DESKTOP_RELEASE_REVALIDATE_SECONDS },
    } as RequestInit & { next: { revalidate: number } });
    if (!response.ok) {
      console.error(
        `[desktop-release] Checksum manifest for ${release.tagName} failed with status ${response.status}`,
      );
      return false;
    }

    const declaredLength = Number(response.headers.get("content-length"));
    if (Number.isFinite(declaredLength) && declaredLength > DESKTOP_CHECKSUM_MANIFEST_MAX_BYTES) {
      console.error(`[desktop-release] Checksum manifest for ${release.tagName} is too large`);
      return false;
    }

    const body = await response.text();
    if (!isValidDesktopChecksumManifest(body, release.version)) {
      console.error(
        `[desktop-release] Checksum manifest for ${release.tagName} does not match the desktop artifact contract`,
      );
      return false;
    }

    return true;
  } catch (error) {
    console.error(
      `[desktop-release] Failed to verify checksum manifest for ${release.tagName}`,
      error,
    );
    return false;
  }
}

export async function fetchLatestStableDesktopRelease(
  fetchImpl: typeof fetch = fetch,
): Promise<DesktopReleaseInfo | null> {
  try {
    const releases: GitHubRelease[] = [];
    let exhaustedReleasePages = false;

    for (let page = 1; page <= DESKTOP_RELEASE_MAX_PAGES; page += 1) {
      const pageUrl =
        page === 1
          ? MUTX_GITHUB_RELEASES_API_URL
          : `${MUTX_GITHUB_RELEASES_API_URL}&page=${page}`;
      const response = await fetchImpl(pageUrl, {
        headers: getGitHubRequestHeaders(),
        next: { revalidate: DESKTOP_RELEASE_REVALIDATE_SECONDS },
      } as RequestInit & { next: { revalidate: number } });

      if (!response.ok) {
        console.error(
          `[desktop-release] GitHub releases page ${page} failed with status ${response.status}`,
        );
        return null;
      }

      const payload: unknown = await response.json();
      if (
        !Array.isArray(payload) ||
        payload.length > DESKTOP_RELEASES_PER_PAGE ||
        !payload.every(isGitHubRelease)
      ) {
        console.error(`[desktop-release] GitHub releases page ${page} returned malformed data`);
        return null;
      }

      releases.push(...payload);
      if (payload.length < DESKTOP_RELEASES_PER_PAGE) {
        exhaustedReleasePages = true;
        break;
      }
    }

    for (const release of getStableDesktopReleaseCandidates(releases)) {
      const normalizedRelease = normalizeDesktopRelease(release);
      if (
        normalizedRelease &&
        (await hasValidDesktopChecksumManifest(normalizedRelease, fetchImpl))
      ) {
        return normalizedRelease;
      }
    }

    console.error(
      exhaustedReleasePages
        ? "[desktop-release] No complete, manifest-verified stable desktop release found in GitHub releases"
        : `[desktop-release] No complete, manifest-verified stable desktop release found within ${DESKTOP_RELEASE_MAX_PAGES} pages`,
    );
    return null;
  } catch (error) {
    console.error("[desktop-release] Failed to fetch latest stable GitHub release", error);
    return null;
  }
}
