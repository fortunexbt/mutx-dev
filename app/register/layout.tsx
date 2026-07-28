import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Create account | MUTX',
  description: 'Create a MUTX operator account for your hosted workspace.',
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
}

export default function RegisterLayout({ children }: { children: React.ReactNode }) {
  return children
}
