import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Sign in | MUTX',
  description: 'Sign in to continue to your MUTX operator workspace.',
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

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children
}
