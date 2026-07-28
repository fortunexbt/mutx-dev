"use client";

import { useEffect, useState } from "react";
import { Sun, Monitor, Moon } from "lucide-react";

type Theme = "light" | "dark" | "system";

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

export function ThemeSwitcher() {
  const [theme, setTheme] = useState<Theme>("dark");

  // Restore from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("mutx-docs-theme") as Theme | null;
    if (stored === "light" || stored === "dark" || stored === "system") {
      setTheme(stored);
      applyTheme(stored);
    } else {
      applyTheme("dark"); // default
    }
  }, []);

  // Listen for system theme changes
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  function select(t: Theme) {
    setTheme(t);
    localStorage.setItem("mutx-docs-theme", t);
    applyTheme(t);
  }

  return (
    <div className="docs-theme-switcher" role="group" aria-label="Select theme">
      <button
        type="button"
        className={`docs-theme-btn${theme === "light" ? " active" : ""}`}
        onClick={() => select("light")}
        title="Light theme"
        aria-label="Use light theme"
        aria-pressed={theme === "light"}
      >
        <Sun size={13} strokeWidth={2} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`docs-theme-btn${theme === "system" ? " active" : ""}`}
        onClick={() => select("system")}
        title="System theme"
        aria-label="Use system theme"
        aria-pressed={theme === "system"}
      >
        <Monitor size={13} strokeWidth={2} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`docs-theme-btn${theme === "dark" ? " active" : ""}`}
        onClick={() => select("dark")}
        title="Dark theme"
        aria-label="Use dark theme"
        aria-pressed={theme === "dark"}
      >
        <Moon size={13} strokeWidth={2} aria-hidden="true" />
      </button>
    </div>
  );
}
