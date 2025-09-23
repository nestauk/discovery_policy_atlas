'use client';

import React, { useMemo, useState } from 'react';
import type { EvidenceItem } from '@/lib/evidenceStore';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';

type Props = {
  issues: EvidenceItem[];
};

export default function EvidenceIssuesTable({ issues }: Props) {
  const [expanded, setExpanded] = useState<Set<string | number>>(new Set());

  const rows = useMemo(() => issues || [], [issues]);

  const toggle = (id: string | number) => {
    const next = new Set(expanded);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setExpanded(next);
  };

  if (!rows || rows.length === 0) {
    return <div className="text-sm text-muted-foreground">No key issues found for this theme.</div>;
  }

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="grid grid-cols-12 gap-4 px-4 py-3 bg-gray-50 rounded-lg border text-sm font-medium text-gray-700">
        <div className="col-span-4">Issue</div>
        <div className="col-span-5">Description</div>
        <div className="col-span-3">Source</div>
      </div>

      {rows.map((item) => {
        const doc = item.document || {};
        const isOpen = expanded.has(item.id);
        return (
          <Card key={String(item.id)} className="border-gray-200">
            <CardContent className="p-0">
              {/* Main Row */}
              <div
                className="grid grid-cols-12 gap-4 px-4 py-3 cursor-pointer"
                onClick={() => toggle(item.id)}
              >
                <div className="col-span-4">
                  <span className="font-medium text-gray-900 text-sm">{item.title}</span>
                </div>
                <div className="col-span-5">
                  <span className="text-sm text-gray-700">{item.brief_description}</span>
                </div>
                <div className="col-span-3">
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    {doc.source && <Badge variant="outline" className="text-xs">{doc.source}</Badge>}
                    {doc.year && <span>{doc.year}</span>}
                    {doc.venue && <span className="truncate">{doc.venue}</span>}
                  </div>
                  {doc.landing_page_url && (
                    <a
                      href={doc.landing_page_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 hover:text-blue-800 hover:underline line-clamp-1"
                    >
                      {doc.title || 'View source'}
                    </a>
                  )}
                </div>
              </div>

              {/* Expanded details */}
              {isOpen && (
                <div className="px-4 pb-4 border-t border-gray-100 bg-gray-50">
                  <div className="pt-4 space-y-3">
                    {/* Supporting evidence */}
                    {item.supporting_evidence && item.supporting_evidence.length > 0 ? (
                      <div className="bg-white rounded p-3 border">
                        <div className="text-xs text-gray-500 mb-2">Supporting Evidence</div>
                        <div className="space-y-3">
                          {item.supporting_evidence.map((ev, idx) => (
                            <blockquote
                              key={idx}
                              className="text-sm text-gray-800 italic border-l-2 border-slate-200 pl-3"
                            >
                              “{ev}”
                            </blockquote>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {/* Countries or other metadata if present */}
                    {item.countries && item.countries.length > 0 && (
                      <div className="text-xs text-gray-600">
                        <span className="font-medium">Countries:</span> {item.countries.join(', ')}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}


