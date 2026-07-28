export const DOCS_HOME_MODEL = {
  title: "MUTX Docs",
  hero: {
    id: "know-the-system",
    kicker: "Operator manual",
    title: "Know the system.",
    description: "Set up MUTX. Run agents. Clear failures.",
    primaryAction: {
      label: "Open MUTX quickstart",
      href: "/docs/quickstart",
    },
    secondaryAction: {
      label: "Read API reference",
      href: "/docs/reference",
    },
  },
  areas: {
    id: "go-by-surface",
    kicker: "By area",
    title: "Go by surface.",
  },
  featured: [
    {
      title: "MUTX Quickstart",
      href: "/docs/quickstart",
      description: "The shortest path to a working MUTX setup.",
    },
    {
      title: "Deployment Quickstart",
      href: "/docs/deployment/quickstart",
      description: "Clone, configure, deploy.",
    },
    {
      title: "Architecture Overview",
      href: "/docs/architecture/overview",
      description: "The system map.",
    },
    {
      title: "API Reference",
      href: "/docs/reference",
      description: "Public contracts and endpoints.",
    },
    {
      title: "Python SDK",
      href: "/sdk",
      description: "Build against MUTX in Python.",
    },
    {
      title: "Troubleshooting",
      href: "/docs/troubleshooting",
      description: "Find and clear common failures.",
    },
  ],
} as const;
