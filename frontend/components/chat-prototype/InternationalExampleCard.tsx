'use client'

import { Globe2 } from 'lucide-react'

interface InternationalExampleCardProps {
  country: string
  title: string
  whyItStandsOut: string
  ukRelevance: string
  url?: string
}

export function InternationalExampleCard({
  country,
  title,
  whyItStandsOut,
  ukRelevance,
  url,
}: InternationalExampleCardProps) {
  return (
    <div className="w-full rounded-2xl border border-sky-200 bg-sky-50 px-4 py-4 shadow-sm">
      <div className="flex items-start gap-2">
        <Globe2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-sky-600" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900">Interesting international example</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            The clearest comparator from outside the UK in this first pass came from{' '}
            <span className="font-medium text-slate-900">{country}</span>.
          </p>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-sky-100 bg-white px-3 py-3">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium leading-6 text-slate-900 hover:text-blue-700 hover:underline"
          >
            {title}
          </a>
        ) : (
          <p className="text-sm font-medium leading-6 text-slate-900">{title}</p>
        )}
        <p className="mt-2 text-sm leading-6 text-slate-600">{whyItStandsOut}</p>
        <p className="mt-2 text-sm leading-6 text-slate-700">{ukRelevance}</p>
      </div>
    </div>
  )
}
