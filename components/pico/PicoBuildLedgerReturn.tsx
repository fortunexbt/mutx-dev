'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'

import { usePicoHref } from '@/lib/pico/navigation'

type PicoBuildLedgerLinkProps = {
  children: ReactNode
  className?: string
  href: string
}

export function PicoBuildLedgerLink({ children, className, href }: PicoBuildLedgerLinkProps) {
  const toHref = usePicoHref()

  return (
    <Link href={toHref(href)} className={className}>
      {children}
    </Link>
  )
}

type PicoBuildLedgerReturnProps = {
  className?: string
  href?: string
  label: string
}

export function PicoBuildLedgerReturn({
  className,
  href = '/onboarding',
  label,
}: PicoBuildLedgerReturnProps) {
  return (
    <PicoBuildLedgerLink href={href} className={className}>
      {label}
      <span aria-hidden="true">↗</span>
    </PicoBuildLedgerLink>
  )
}
