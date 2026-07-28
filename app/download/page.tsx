import type { Metadata } from "next";

import MacDownloadPage from "./macos/page";
import { buildPageMetadata } from "@/lib/seo";

export const revalidate = 900;

export const metadata: Metadata = {
  title: "Download MUTX | MUTX",
  description:
    "Check MUTX desktop availability for your platform and access current release notes.",
  ...buildPageMetadata({
    title: "Download MUTX | MUTX",
    description:
      "Check MUTX desktop availability for your platform and access current release notes.",
    path: "/download",
  }),
};

export default MacDownloadPage;
