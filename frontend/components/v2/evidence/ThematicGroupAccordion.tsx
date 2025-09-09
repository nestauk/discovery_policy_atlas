'use client';

import React from 'react';
import type { ThematicGroup } from '@/lib/evidenceStore';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import ItemsListView from '@/components/v2/evidence/ItemsListView';

type ThematicGroupAccordionProps = {
  projectId: string;
  thematicGroups: ThematicGroup[];
  themeType: 'intervention' | 'issue';
};

export default function ThematicGroupAccordion({ projectId, thematicGroups, themeType }: ThematicGroupAccordionProps) {
  const groups = Array.isArray(thematicGroups) ? thematicGroups : [];

  return (
    <Accordion type="single" collapsible className="w-full space-y-3">
      {groups.map((thematicGroup: ThematicGroup) => (
        <div key={thematicGroup.id} className="rounded-lg border bg-white shadow-sm">
          <AccordionItem value={String(thematicGroup.id)} className="border-0">
            <AccordionTrigger className="px-4 py-3 hover:no-underline">
              <div className="flex w-full items-start justify-between gap-3 text-left">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-900 truncate">
                      {thematicGroup.theme_title}
                    </span>
                  </div>
                  {thematicGroup.theme_summary && (
                    <div className="mt-1 text-sm text-slate-600 line-clamp-2">
                      {thematicGroup.theme_summary}
                    </div>
                  )}
                </div>
                <div className="flex-shrink-0">
                  <Badge variant="secondary" className="text-xs">
                    {thematicGroup.item_count}
                  </Badge>
                </div>
              </div>
            </AccordionTrigger>
            <AccordionContent className="px-4 pb-4 bg-slate-50 border-t rounded-b-lg">
              <ItemsListView projectId={projectId} themeId={thematicGroup.id} themeType={themeType} />
            </AccordionContent>
          </AccordionItem>
        </div>
      ))}
    </Accordion>
  );
}


