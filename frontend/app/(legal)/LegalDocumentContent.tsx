import React from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'

function isStandaloneStrong(children: React.ReactNode): children is React.ReactElement {
  const childNodes = React.Children.toArray(children)
  return (
    childNodes.length === 1 &&
    React.isValidElement(childNodes[0]) &&
    childNodes[0].type === 'strong'
  )
}

const markdownComponents: Components = {
  h3: ({ children }) => (
    <h1 className="mb-8 text-3xl font-semibold leading-tight tracking-tight text-slate-900">{children}</h1>
  ),
  p: ({ children }) => {
    if (isStandaloneStrong(children)) {
      return (
        <h2 className="mt-8 mb-3 text-2xl font-semibold leading-tight text-slate-900">
          {children}
        </h2>
      )
    }

    return <p className="my-4 text-base leading-7 text-slate-800">{children}</p>
  },
  ul: ({ children }) => <ul className="my-4 list-disc space-y-2 pl-7">{children}</ul>,
  li: ({ children }) => <li className="pl-1 text-base leading-7 text-slate-800">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-slate-900">{children}</strong>,
  a: ({ href, children }) => (
    <a
      href={href}
      className="font-medium text-slate-900 underline decoration-slate-400 underline-offset-2 transition-colors hover:text-slate-700"
      rel="noreferrer"
      target="_blank"
    >
      {children}
    </a>
  ),
}

export function LegalDocumentContent({ markdown }: { markdown: string }) {
  return (
    <section className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
      <article className="text-slate-900">
        <ReactMarkdown components={markdownComponents}>{markdown}</ReactMarkdown>
      </article>
    </section>
  )
}
