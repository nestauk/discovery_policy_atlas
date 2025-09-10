'use client';

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { EvidenceItem } from '@/lib/evidenceStore';

type Props = { item: EvidenceItem };

function directionBadgeClasses(direction: string) {
  switch (direction) {
    case 'Positive':
      return 'bg-green-100 text-green-800 border-green-200';
    case 'Negative':
      return 'bg-red-100 text-red-800 border-red-200';
    case 'Neutral':
      return 'bg-slate-100 text-slate-800 border-slate-200';
    case 'Mixed':
      return 'bg-amber-100 text-amber-800 border-amber-200';
    default:
      return 'bg-slate-100 text-slate-800 border-slate-200';
  }
}

export default function EvidenceCard({ item }: Props) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{item.title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {item.brief_description && (
          <p className="text-sm text-slate-700">{item.brief_description}</p>
        )}

        <div className="text-sm">
          <span className="text-slate-500">Frequency:</span>{' '}
          <span className="font-medium">{item.frequency}</span>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-900">Outcomes</div>
          <div className="space-y-3">
            {item.outcomes?.length ? (
              item.outcomes.map((o, idx) => (
                <div key={idx} className="rounded-md border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-sm font-medium text-slate-900">{o.outcome}</div>
                    <Badge variant="outline" className={directionBadgeClasses(o.direction_of_effect)}>
                      {o.direction_of_effect}
                    </Badge>
                  </div>
                  <div className="mt-2 grid grid-cols-1 gap-1 text-sm text-slate-700 sm:grid-cols-2">
                    <div>
                      <span className="text-slate-500">Effect size:</span>{' '}
                      <span className="font-medium">{o.effect_size || '—'}</span>
                    </div>
                    <div>
                      <span className="text-slate-500">Significance:</span>{' '}
                      <span className="font-medium">{o.significance || '—'}</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-slate-500">No outcomes available.</div>
            )}
          </div>
        </div>

        <div className="space-y-2">
          <div className="text-sm font-semibold text-slate-900">Supporting Evidence</div>
          <div className="space-y-3">
            {item.supporting_evidence?.length ? (
              item.supporting_evidence.map((ev, idx) => (
                <blockquote
                  key={idx}
                  className="border-l-2 border-slate-300 pl-3 italic text-sm text-slate-700"
                >
                  “{ev}”
                </blockquote>
              ))
            ) : (
              <div className="text-sm text-slate-500">No supporting evidence provided.</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

