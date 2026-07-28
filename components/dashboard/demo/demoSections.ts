export const DEMO_SECTIONS = [
  "overview",
  "agents",
  "deployments",
  "runs",
  "environments",
  "access",
  "connectors",
  "audit",
  "usage",
  "settings",
] as const;

export type DemoSection = (typeof DEMO_SECTIONS)[number];

export function isDemoSection(value: string): value is DemoSection {
  return DEMO_SECTIONS.includes(value as DemoSection);
}

export function getDemoSectionHref(section: DemoSection) {
  return section === "overview" ? "/control" : `/control/${section}`;
}
