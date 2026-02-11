export const FOOTER_DISCLAIMER_TEXT =
  'Policy Atlas is powered by AI and may make mistakes. The outputs are ' +
  'a synthesis of third-party evidence from academic and grey literature, they ' +
  'do not necessarily reflect the official views of Nesta. They are intended ' +
  'for informational purposes only and should be cross-referenced with ' +
  'primary sources before being used for decision-making.'

export function Footer({ className = '' }: { className?: string }) {
  return (
    <footer className={`flex-shrink-0 mt-auto border-t border-slate-200 bg-slate-50 px-4 py-4 ${className}`.trim()}>
      <p className="text-xs text-slate-600 max-w-4xl mx-auto text-center leading-relaxed">
        {FOOTER_DISCLAIMER_TEXT}
      </p>
    </footer>
  )
}
