import Link from 'next/link'

export const FOOTER_DISCLAIMER_TEXT =
  'Policy Atlas is powered by AI and may make mistakes. The outputs are ' +
  'a synthesis of third-party evidence from academic and grey literature, they ' +
  'do not necessarily reflect the official views of Nesta. They are intended ' +
  'for informational purposes only and should be cross-referenced with ' +
  'primary sources before being used for decision-making.'

export function Footer({ className = '' }: { className?: string }) {
  return (
    <footer className={`flex-shrink-0 border-t border-slate-200 bg-slate-50 px-4 py-4 ${className}`.trim()}>
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-2 text-center">
        <p className="text-xs leading-relaxed text-slate-600">{FOOTER_DISCLAIMER_TEXT}</p>
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <Link href="/privacy" className="hover:underline">
            Privacy policy
          </Link>
          <span aria-hidden="true">|</span>
          <Link href="/terms" className="hover:underline">
            Terms of use
          </Link>
        </div>
      </div>
    </footer>
  )
}
