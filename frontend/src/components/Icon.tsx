// Small inline icon set (stroke icons, 24px grid). No icon library needed.
const PATHS: Record<string, string> = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  jobs: "M4 7h16v12H4zM9 7V5h6v2M4 12h16",
  apps: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5",
  mail: "M3 6h18v12H3zM3 7l9 6 9-6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  cv: "M7 3h10v18H7zM10 7h4M10 11h4M10 15h2",
  globe: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18",
  building: "M5 21V4h9v17M14 9h5v12M8 8h2M8 12h2M8 16h2",
  layout: "M4 4h16v16H4zM4 10h16M10 10v10",
  plug: "M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0zM12 17v4",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6 6 18",
  out: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  share: "M12 3v12M8 7l4-4 4 4M5 13v7h14v-7",
  download: "M12 3v12M8 11l4 4 4-4M5 20h14",
  external: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  check: "M5 12l5 5L19 7",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  shield: "M12 3 4 6v6c0 4.5 3.4 8 8 9 4.6-1 8-4.5 8-9V6z",
};

export default function Icon({ name, size = 20, label }: { name: keyof typeof PATHS | string; size?: number; label?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
         strokeLinecap="round" strokeLinejoin="round" role={label ? "img" : undefined} aria-label={label}
         aria-hidden={label ? undefined : true} focusable="false">
      <path d={PATHS[name] ?? PATHS.spark} />
    </svg>
  );
}
