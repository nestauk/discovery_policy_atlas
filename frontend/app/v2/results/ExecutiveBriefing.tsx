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
          <div>
            We are preparing the executive briefing. Please come back a bit later.
          </div>
        )}
      </CardContent>
    </Card>
  );
}


