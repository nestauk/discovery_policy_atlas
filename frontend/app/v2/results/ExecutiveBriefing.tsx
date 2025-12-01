'use client'

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import ReactMarkdown from "react-markdown";

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
          <div className="prose prose-slate max-w-none">
            <ReactMarkdown
              skipHtml
              components={{
                ul: (props) => (
                  <ul className="list-disc pl-6 my-2" {...props} />
                ),
                ol: (props) => (
                  <ol className="list-decimal pl-6 my-2" {...props} />
                ),
                li: (props) => <li className="my-1" {...props} />,
              }}
            >
              {briefing}
            </ReactMarkdown>
          </div>
        ) : (
          <div>
            We are preparing the executive briefing. Please come back a bit later.
          </div>
        )}
      </CardContent>
    </Card>
  );
}


