'use client'

import Link from 'next/link'
import { SignInButton } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip } from '@/components/ui/tooltip'
import { motion } from 'framer-motion'
import { ArrowRight, ChevronDown } from 'lucide-react'
import FeatureShowcase from '@/components/landing/FeatureShowcase'

interface LandingPageContentProps {
  isLoggedIn: boolean
}

export default function LandingPageContent({ isLoggedIn }: LandingPageContentProps) {
  const scrollToFeatures = () => {
    document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="relative min-h-screen bg-white">

      {/* Hero Section */}
      <section className="relative min-h-[85vh] flex items-center justify-center">
        <div className="max-w-4xl mx-auto space-y-8 p-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="space-y-12"
          >
            <div className="text-center space-y-4">
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="flex items-center justify-center gap-3"
              >
                <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
                  {isLoggedIn ? 'Welcome to Policy Atlas' : 'Policy Atlas'}
                </h1>
                <Tooltip
                  content={
                    <p className="max-w-xs">
                      Alpha means this is an early prototype with limited functionality.
                      Features may be incomplete, unstable, or subject to change.
                      We&apos;re actively developing and improving the tool.
                    </p>
                  }
                >
                  <Badge
                    variant="default"
                    className="text-sm bg-blue-600 hover:bg-blue-700 text-white font-semibold px-3 py-1 -mt-2"
                  >
                    ALPHA
                  </Badge>
                </Tooltip>
              </motion.div>

              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="text-xl text-muted-foreground max-w-2xl mx-auto leading-relaxed"
              >
                AI-powered evidence discovery for UK policymakers, developed by{' '}
                <Link
                  href="https://www.nesta.org.uk"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:text-blue-800 transition-colors"
                >
                  Nesta
                </Link>
              </motion.p>
            </div>

            {/* CTA buttons */}
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="text-center"
            >
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                {isLoggedIn ? (
                  <>
                    <Link href="/search">
                      <Button
                        size="lg"
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/30"
                      >
                        Search
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </Link>
                    <Link href="/projects">
                      <Button
                        size="lg"
                        variant="outline"
                        className="flex items-center gap-2 transition-all hover:bg-muted"
                      >
                        Projects
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </Link>
                  </>
                ) : (
                  <>
                    <SignInButton mode="modal">
                      <Button
                        size="lg"
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/30"
                      >
                        Sign in to get started
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </SignInButton>
                    <Link href="https://www.nesta.org.uk/project/policy-atlas-harnessing-ai-to-improve-policy-design/">
                      <Button
                        size="lg"
                        variant="outline"
                        className="flex items-center gap-2 transition-all hover:bg-muted"
                      >
                        Learn more
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                    </Link>
                  </>
                )}
              </div>
            </motion.div>
          </motion.div>

          {/* Scroll indicator */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.8 }}
            className="flex justify-center pt-12"
          >
            <button
              onClick={scrollToFeatures}
              className="group flex flex-col items-center gap-2 text-muted-foreground/60 hover:text-muted-foreground transition-colors cursor-pointer"
            >
              <span className="text-base font-medium">Discover how it works</span>
              <motion.div
                animate={{ y: [0, 6, 0] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}
              >
                <ChevronDown className="h-5 w-5" />
              </motion.div>
            </button>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <div id="features">
        <FeatureShowcase />
      </div>

      {/* Final CTA Section */}
      <motion.section
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true, margin: '-100px' }}
        transition={{ duration: 0.8 }}
        className="py-12 lg:py-16"
      >
        <div className="max-w-3xl mx-auto px-6 text-center space-y-8">
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="text-3xl lg:text-4xl font-bold tracking-tight"
          >
            Start discovering evidence today
          </motion.h2>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-lg text-muted-foreground"
          >
            Whether you&apos;re exploring a new policy area or diving into specific interventions,
            Policy Atlas helps you find and synthesise the evidence you need.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="flex flex-col sm:flex-row gap-4 justify-center pt-4"
          >
            {isLoggedIn ? (
              <>
                <Link href="/search">
                  <Button
                    size="lg"
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/30"
                  >
                    Start searching
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/projects">
                  <Button
                    size="lg"
                    variant="outline"
                    className="flex items-center gap-2 transition-all hover:bg-muted"
                  >
                    Browse projects
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </>
            ) : (
              <>
                <SignInButton mode="modal">
                  <Button
                    size="lg"
                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 shadow-lg shadow-blue-600/20 transition-all hover:shadow-xl hover:shadow-blue-600/30"
                  >
                    Sign in to get started
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </SignInButton>
                <Link href="https://www.nesta.org.uk/project/policy-atlas-harnessing-ai-to-improve-policy-design/">
                  <Button
                    size="lg"
                    variant="outline"
                    className="flex items-center gap-2 transition-all hover:bg-muted"
                  >
                    Learn more
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </>
            )}
          </motion.div>
        </div>
      </motion.section>
    </div>
  )
}

