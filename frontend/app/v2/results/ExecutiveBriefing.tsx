'use client'

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface ExecutiveBriefingProps {
  briefing: string;
}

export function ExecutiveBriefing({ briefing }: ExecutiveBriefingProps) {
  // Log briefing status for debugging
  console.log('[ExecutiveBriefing] Rendering with briefing:', {
    hasBriefing: !!briefing,
    length: briefing?.length || 0,
    preview: briefing?.substring(0, 100) || 'none'
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Executive Briefing</CardTitle>
      </CardHeader>
      <CardContent>
        {briefing ? (
          <p className="text-base leading-relaxed whitespace-pre-wrap">{briefing}</p>
        ) : (
          <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-yellow-800 text-sm">
            Executive briefing is currently unavailable. Please try again later.
          </div>
        )}
      </CardContent>
    </Card>
  );
}


