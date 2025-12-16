'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { ArrowRight } from 'lucide-react'

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto space-y-8 p-8 pt-32">
      {/* Welcome Section */}
      <section className="space-y-12">
        <div className="text-center space-y-0">
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
          <p className="text-lg max-w-2xl mx-auto">
            Find evidence on policy interventions, or browse already existing projects
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link href="/search">
              <Button size="lg" className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700">
                Search
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/projects">
              <Button size="lg" variant="outline" className="flex items-center gap-2">
                Projects
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  )
}