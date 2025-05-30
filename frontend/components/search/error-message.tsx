import { Card, CardContent } from '@/components/ui/card'

interface ErrorMessageProps {
  message: string
}

export function ErrorMessage({ message }: ErrorMessageProps) {
  return (
    <Card className="error-card">
      <CardContent className="pt-6">
        <p className="text-destructive">{message}</p>
      </CardContent>
    </Card>
  )
}