'use client'

import { useRef, useState } from 'react'
import { motion, useInView } from 'framer-motion'
import { Search, Sparkles, BarChart3, FileText, MessageCircle, Rocket } from 'lucide-react'

interface Feature {
  id: string
  number: string
  title: string
  description: string
  icon: React.ReactNode
  gradient: string
  accentColor: string
  media: string
}

const features: Feature[] = [
  {
    id: 'query',
    number: '01',
    title: 'Enter your query',
    description: 'Describe your policy question in natural language. Our AI-powered search helps you refine the query to find relevant evidence across thousands of academic papers and policy documents.',
    icon: <Search className="w-8 h-8" />,
    gradient: 'from-blue-500/20 via-cyan-500/10 to-transparent',
    accentColor: 'text-blue-500',
    media: '/screenshots/01-enter-query.png',
  },
  {
    id: 'synthesise',
    number: '02',
    title: 'Synthesise evidence',
    description: 'Our AI automatically synthesises findings from multiple sources, summarising key interventions and outcomes to give you an overview of the evidence landscape.',
    icon: <Sparkles className="w-8 h-8" />,
    gradient: 'from-violet-500/20 via-purple-500/10 to-transparent',
    accentColor: 'text-violet-500',
    media: '/screenshots/02-synthesise.png',
  },
  {
    id: 'interventions',
    number: '03',
    title: 'Assess interventions',
    description: 'Explore a structured breakdown of policy interventions with their evidence strength and measured outcomes. Compare approaches to find what works best.',
    icon: <BarChart3 className="w-8 h-8" />,
    gradient: 'from-emerald-500/20 via-green-500/10 to-transparent',
    accentColor: 'text-emerald-500',
    media: '/screenshots/03-interventions.png',
  },
  {
    id: 'browse',
    number: '04',
    title: 'Browse the evidence',
    description: 'Look through the individual papers and documents. Read summaries and access the original sources to find what you need.',
    icon: <FileText className="w-8 h-8" />,
    gradient: 'from-amber-500/20 via-orange-500/10 to-transparent',
    accentColor: 'text-amber-500',
    media: '/screenshots/04-browse-evidence.png',
  },
  {
    id: 'assistant',
    number: '05',
    title: 'Go deeper with the Assistant',
    description: 'Ask questions to our AI assistant that is grounded in your evidence base. Ask follow-up questions and explore specific aspects of the research in detail.',
    icon: <MessageCircle className="w-8 h-8" />,
    gradient: 'from-rose-500/20 via-pink-500/10 to-transparent',
    accentColor: 'text-rose-500',
    media: '/screenshots/05-assistant.png',
  },
]


function FeatureCard({ feature, index }: { feature: Feature; index: number }) {
  const ref = useRef<HTMLDivElement>(null)
  const isInView = useInView(ref, { once: true, margin: '-100px' })
  const isEven = index % 2 === 0
  const [mediaLoaded, setMediaLoaded] = useState(false)
  const [mediaError, setMediaError] = useState(false)
  
  const isVideo = feature.media.endsWith('.mp4') || feature.media.endsWith('.webm')

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 60 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 60 }}
      transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
      className="relative"
    >
      <div
        className={`flex flex-col ${isEven ? 'lg:flex-row' : 'lg:flex-row-reverse'} gap-8 lg:gap-16 items-center`}
      >
        {/* Content Side */}
        <motion.div
          initial={{ opacity: 0, x: isEven ? -40 : 40 }}
          animate={isInView ? { opacity: 1, x: 0 } : { opacity: 0, x: isEven ? -40 : 40 }}
          transition={{ duration: 0.8, delay: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="flex-1 space-y-6"
        >
          <div className="flex items-center gap-4">
            <span className="font-mono text-sm tracking-widest text-muted-foreground/60">
              {feature.number}
            </span>
            <div className={`p-3 rounded-xl bg-gradient-to-br ${feature.gradient} backdrop-blur-sm border border-white/10`}>
              <div className={feature.accentColor}>{feature.icon}</div>
            </div>
          </div>

          <h3 className="text-3xl lg:text-4xl font-bold tracking-tight">{feature.title}</h3>

          <p className="text-lg text-muted-foreground leading-relaxed max-w-xl">
            {feature.description}
          </p>
        </motion.div>

        {/* Image Side */}
        <motion.div
          initial={{ opacity: 0, x: isEven ? 40 : -40, scale: 0.95 }}
          animate={isInView ? { opacity: 1, x: 0, scale: 1 } : { opacity: 0, x: isEven ? 40 : -40, scale: 0.95 }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="flex-1 w-full"
        >
          <div className="relative group">
            {/* Glow effect */}
            <div
              className={`absolute -inset-4 bg-gradient-to-r ${feature.gradient} rounded-3xl blur-2xl opacity-40 group-hover:opacity-60 transition-opacity duration-500`}
            />

            {/* Media container */}
            <div className="relative aspect-[16/10]">
              {/* Video or Image element */}
              {!mediaError && isVideo ? (
                <video
                  src={feature.media}
                  autoPlay
                  loop
                  muted
                  playsInline
                  className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-500 ${mediaLoaded ? 'opacity-100' : 'opacity-0'}`}
                  onLoadedData={() => setMediaLoaded(true)}
                  onError={() => setMediaError(true)}
                />
              ) : !mediaError ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={feature.media}
                  alt={`Screenshot of ${feature.title}`}
                  className={`absolute inset-0 w-full h-full object-contain transition-opacity duration-500 ${mediaLoaded ? 'opacity-100' : 'opacity-0'}`}
                  onLoad={() => setMediaLoaded(true)}
                  onError={() => setMediaError(true)}
                />
              ) : null}
              
              {/* Placeholder content (shows when media hasn't loaded or failed) */}
              <div className={`absolute inset-0 flex flex-col items-center justify-center p-8 rounded-2xl border border-white/10 bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-800 dark:to-gray-900 shadow-2xl transition-opacity duration-500 ${mediaLoaded && !mediaError ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
                <div className={`${feature.accentColor} opacity-30 mb-4`}>
                  <div className="w-20 h-20">
                    {feature.icon}
                  </div>
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-muted-foreground/60 mb-2">
                    Add screenshot
                  </p>
                  <p className="text-xs text-muted-foreground/40 font-mono">
                    {feature.media}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </motion.div>
  )
}

export default function FeatureShowcase() {
  const containerRef = useRef<HTMLDivElement>(null)
  const titleInView = useInView(containerRef, { once: true, margin: '-50px' })

  return (
    <section className="relative pt-24 pb-12 lg:pt-32 lg:pb-16">
      {/* Background decoration */}
      <div className="absolute inset-0 -z-10 overflow-hidden">
        <div className="absolute top-1/4 left-0 w-96 h-96 bg-blue-500/5 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 right-0 w-96 h-96 bg-violet-500/5 rounded-full blur-3xl" />
      </div>

      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        {/* Section header */}
        <motion.div
          ref={containerRef}
          initial={{ opacity: 0, y: 30 }}
          animate={titleInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 30 }}
          transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="text-center mb-20 lg:mb-32"
        >
          <motion.p
            initial={{ opacity: 0 }}
            animate={titleInView ? { opacity: 1 } : { opacity: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="font-mono text-sm tracking-widest text-blue-600 dark:text-blue-400 mb-4"
          >
            HOW IT WORKS
          </motion.p>
          <h2 className="text-3xl lg:text-5xl font-bold tracking-tight mb-6">
            From question to insight
            <br />
            <span className="text-muted-foreground/60">in five steps</span>
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Policy Atlas streamlines your evidence discovery workflow, 
            from initial query to actionable insights.
          </p>
        </motion.div>

        {/* Features */}
        <div className="space-y-24 lg:space-y-40">
          {features.map((feature, index) => (
            <FeatureCard key={feature.id} feature={feature} index={index} />
          ))}
        </div>

        {/* Coming Soon Section */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.8, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="mt-24 lg:mt-40"
        >
          <div className="relative rounded-3xl overflow-hidden">
            {/* Background gradient */}
            <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-pink-500/10" />
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-500/10 via-transparent to-transparent" />
            
            {/* Content */}
            <div className="relative px-8 py-16 lg:px-16 lg:py-20">
              <div className="flex items-center gap-3 mb-6">
                <span className="font-mono text-sm tracking-widest text-muted-foreground/60">06</span>
                <div className="p-3 rounded-xl bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-transparent backdrop-blur-sm border border-white/10">
                  <Rocket className="w-8 h-8 text-indigo-500" />
                </div>
              </div>

              <h3 className="text-3xl lg:text-4xl font-bold tracking-tight mb-4">
                More to come
              </h3>
              
              <p className="text-lg text-muted-foreground max-w-2xl mb-12">
                With your feedback, we are actively improving this tool, making it more reliable and tailored to policymakers needs.
              </p>
              <p className="text-lg text-muted-foreground max-w-2xl mb-12">
                We&apos;re also considering other powerful capabilities, such as policy simulations and analysis of intervention transferability to your local context.
              </p>
            </div>
          </div>
        </motion.div>

      </div>
    </section>
  )
}

