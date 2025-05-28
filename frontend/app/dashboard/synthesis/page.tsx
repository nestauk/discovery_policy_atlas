import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function SynthesisPage() {
  return (
    <div className="max-w-4xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>Synthesis</CardTitle>
          <CardDescription>
            AI-powered research synthesis coming soon
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            This feature will allow you to synthesize insights from multiple research papers.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}