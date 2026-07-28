export function getNextDesktopTabIndex(
  key: string,
  currentIndex: number,
  tabCount: number,
  isRtl: boolean,
) {
  if (tabCount <= 0) {
    return currentIndex;
  }

  if (key === "Home") {
    return 0;
  }

  if (key === "End") {
    return tabCount - 1;
  }

  const delta = key === "ArrowRight" ? (isRtl ? -1 : 1) : isRtl ? 1 : -1;
  return (currentIndex + delta + tabCount) % tabCount;
}
