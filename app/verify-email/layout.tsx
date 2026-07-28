import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("pico.authRecovery.verifyEmail");

  return {
    title: `${t("eyebrow")} | MUTX`,
    description: t("description"),
    alternates: {
      canonical: null,
    },
    openGraph: null,
    twitter: null,
    robots: {
      index: false,
      follow: false,
      nocache: true,
    },
  };
}

export default function VerifyEmailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
