'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ArrowRight } from 'lucide-react'

export default function V2HomePage() {
  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8">
      {/* Welcome Section */}
      <section className="space-y-6">
        <div className="text-center space-y-4">
          <div className="flex items-center justify-center gap-3">
            <h1 className="text-4xl font-bold tracking-tight">Welcome to Policy Atlas</h1>
            <Tooltip content={
              <p className="max-w-xs">
                Alpha means this is an early prototype with limited functionality. 
                Features may be incomplete, unstable, or subject to change. 
                We&apos;re actively developing and improving the tool.
              </p>
            }>
              <Badge variant="default" className="text-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold px-3 py-1 -mt-2">ALPHA</Badge>
            </Tooltip>
          </div>
          <p className="text-xl max-w-4xl mx-auto leading-relaxed">
            AI-powered tool for UK policymakers, developed by <Link href="https://www.nesta.org.uk" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800">Nesta</Link>
          </p>
        </div>

        <div className="text-center space-y-6">
          <h2 className="text-2xl font-semibold">Get Started</h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Create a new analysis project to search, screen, and explore policy and research documents
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link href="/v2/search/chat">
              <Button size="lg" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700">
                Chat Search (New)
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/v2/projects">
              <Button size="lg" variant="outline" className="flex items-center gap-2">
                Browse Projects
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}