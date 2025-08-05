'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Search, Brain, Beaker, ExternalLink, Mail, ArrowRight, ChevronDown, Database } from 'lucide-react'
import { useState } from 'react'

export default function HomePage() {
  const [isDataSourcesOpen, setIsDataSourcesOpen] = useState(false)

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Table of Contents - Commented out for now */}
      {/* <Card className="sticky top-6 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Table of Contents
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {[
              { id: 'welcome', label: 'Welcome' },
              { id: 'getting-started', label: 'Getting Started' },
              { id: 'project-vision', label: 'Project Vision' },
              { id: 'team', label: 'Meet the Team' },
            ].map((item) => (
              <Button
                key={item.id}
                variant="outline"
                size="sm"
                onClick={() => scrollToSection(item.id)}
                className="text-sm"
              >
                {item.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card> */}

      {/* Welcome Section */}
      <section id="welcome" className="space-y-6">
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-bold tracking-tight">Welcome to Policy Atlas</h1>
          <p className="text-xl max-w-4xl mx-auto leading-relaxed">
            Policy Atlas is a new AI-powered tool being developed by <Link href="https://www.nesta.org.uk" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">Nesta</Link> to help UK policymakers quickly explore, 
            synthesise and simulate policy evidence. 
            It will enable faster, deeper engagement with complex research and policy data, supporting more innovative and effective policymaking.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>You can use Policy Atlas to:</CardTitle>
            <CardDescription>
              
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid md:grid-cols-3 gap-4">
              <div className="flex items-start gap-3">
                <Search className="h-5 w-5 text-blue-600 mt-1" />
                <div>
                  <h4 className="font-medium">Search and Screen</h4>
                  <p className="text-sm text-muted-foreground">
                    Search and screen policy and research documents
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Brain className="h-5 w-5 text-green-600 mt-1" />
                <div>
                  <h4 className="font-medium">Synthesise <Badge variant="secondary">Coming Soon</Badge></h4> 
                  <p className="text-sm text-muted-foreground">
                   Summarise and visualise policy and research data
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Beaker className="h-5 w-5 text-purple-600 mt-1" />
                <div>
                  <h4 className="font-medium">Simulate <Badge variant="secondary">Coming Soon</Badge></h4>
                  <p className="text-sm text-muted-foreground">
                    Simulate policy interventions
                  </p>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3 pt-4">
                          <Link href="/agent">
              <Button className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700">
                  <Brain className="h-4 w-4" />
                  New: AI Evidence Synthesis
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/dashboard/search">
                <Button variant="outline" className="flex items-center gap-2">
                  <Search className="h-4 w-4" />
                  Classic Search
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="https://www.nesta.org.uk/project/policy-atlas-harnessing-ai-to-improve-policy-design/" target="_blank" rel="noopener noreferrer">
                <Button variant="ghost" className="flex items-center gap-2">
                  Learn more about the Policy Atlas project
                  <ExternalLink className="h-4 w-4" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* Getting Started Guide */}
      <section id="getting-started" className="space-y-8">
        <div className="text-center">
          <h2 className="text-3xl font-bold tracking-tight">Getting Started</h2>
          <p className="text-muted-foreground mt-2">
            Follow this tutorial to make the most of Policy Atlas
          </p>
        </div>

        <div className="space-y-12">
          {/* Step 1: Search */}
          <div className="space-y-6">
            <h3 className="text-2xl font-semibold flex items-center gap-2">
              <Search className="h-6 w-6 text-blue-600" />
              Search
            </h3>
            
            <div className="space-y-4">
              <p className="text-lg leading-relaxed">
                Policy Atlas search function allows you to quickly search and process hundreds of policy and research documents (and we plan to scale to thousands and more).
                The app uses AI (large language models) to help screen the documents according to your search criteria, and it can 
                also extract relevant information from the documents as per your instructions. In this way, it can save a lot of time and effort, by doing a first pass of screening and processing.
              </p>

              <p className="text-lg leading-relaxed">
                Policy Atlas currently supports policy (
                <Link href="https://www.overton.io" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">
                  Overton
                </Link>) 
                and research (
                <Link href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">
                  OpenAlex
                </Link>) publication data.
              </p>
              
              {/* Data Sources Collapsible Section */}
              <div className="mt-4">
                <Collapsible open={isDataSourcesOpen} onOpenChange={setIsDataSourcesOpen}>
                  <CollapsibleTrigger asChild>
                    <Button variant="outline" className="flex items-center gap-2">
                      <Database className="h-4 w-4" />
                      Learn more about our data sources
                      <ChevronDown className={`h-4 w-4 transition-transform ${isDataSourcesOpen ? 'rotate-180' : ''}`} />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-4 space-y-4">
                    <div className="grid md:grid-cols-2 gap-4">
                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <div className="w-3 h-3 bg-black rounded-full"></div>
                            Overton
                          </CardTitle>
                          <CardDescription>
                            Policy document database
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-muted-foreground mb-3">
                            Overton is the world&apos;s largest policy document database, containing millions of policy documents, 
                            parliamentary records, government reports, and think tank publications from around the world.
                          </p>
                          <Link href="https://www.overton.io" target="_blank" rel="noopener noreferrer">
                            <Button variant="outline" size="sm" className="flex items-center gap-2">
                              Visit Overton
                              <ExternalLink className="h-3 w-3" />
                            </Button>
                          </Link>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader>
                          <CardTitle className="flex items-center gap-2">
                            <div className="w-3 h-3 bg-black rounded-full"></div>
                            OpenAlex
                          </CardTitle>
                          <CardDescription>
                            Academic research database
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <p className="text-sm text-muted-foreground mb-3">
                            OpenAlex is a comprehensive database of academic research, including journal articles, 
                            books, datasets, and other scholarly outputs from universities and research institutions worldwide.
                          </p>
                          <Link href="https://openalex.org" target="_blank" rel="noopener noreferrer">
                            <Button variant="outline" size="sm" className="flex items-center gap-2">
                              Visit OpenAlex
                              <ExternalLink className="h-3 w-3" />
                            </Button>
                          </Link>
                        </CardContent>
                      </Card>
                    </div>
                  </CollapsibleContent>
                </Collapsible>
              </div>

              {/* Overton Section */}
              <div className="space-y-4">
                <h4 className="text-xl font-semibold">Overton</h4>
                
                <p className="text-lg leading-relaxed">
                  Overton source supports free text searches - the more detailed your search text, the more precise will be the results.
                  This is thanks to &ldquo;semantic search&rdquo;, which is turned on by default.
                </p>

                {/* Overton Video */}
                <div className="bg-muted rounded-lg p-4">
                  <div className="aspect-video w-full">
                                         <iframe
                       className="w-full h-full rounded border-0"
                       src="https://www.youtube.com/embed/hx22EQZK1jk?rel=0"
                       title="Overton Search Tutorial"
                       allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                       allowFullScreen
                     ></iframe>
                  </div>
                </div>
                <h5 className="text-lg font-semibold">Advanced Options</h5>
                <p className="text-lg leading-relaxed">
                  The <strong>Advanced Options</strong> allow you to specify maximum number of results to retrieve from the database (presently the limit is 1000 documents), date range, and inclusion criteria.
                  We recommend starting with a small number of maximum results (20-50), refining your search parameters and then increasing the number of maximum results.
                </p>

                <p className="text-lg leading-relaxed">
                  The results are ranked in terms of semantic similarity to your search query. In this way, the retrieved results are the most relevant to your search query.
                  By specifying the number of maximum results, you control the number of top-most relevant results you get.
                </p>

                <p className="text-lg leading-relaxed">
                  You also specify source country or region, and source type, e.g., Think Tank, Government or Inter-Governmental Organisation (IGOs). IGOs include organisations such as OECD and WHO.
                </p>
                <h5 className="text-lg font-semibold">AI Screening</h5>
                <p className="text-lg leading-relaxed">
                  You can then use <strong>AI screening</strong> of the results (enabled by default) - this is where make a step from simple database search to a more sophisticated screening and processing.
                </p>
                
                <p className="text-lg leading-relaxed">
                  You can specify inclusion criteria (and exclusion criteria) for the screening. 
                </p>
                
                <p className="text-lg leading-relaxed">
                  You can also specify details to extract from the documents. For example, you can extract country mentioned in the document, or the type of intervention that was used, or the reported sample size etc. 
                  You can provide arbitrary instructions (similar to a large language model prompt). The extracted fields will be saved as extra columns in the output CSV table
                </p>
                <h5 className="text-lg font-semibold">CSV output</h5>
                <p className="text-lg leading-relaxed">
                  Finally, you can download the results as a CSV table and use them in your own analysis with Google Sheets, Excel, or other tools.
                </p>
              </div>

              {/* OpenAlex Section */}
              <div className="space-y-4">
                <h4 className="text-xl font-semibold">OpenAlex</h4>

                <p className="text-lg leading-relaxed">
                  The search parameters for OpenAlex are similar to Overton, with the following differences.
                </p>

                <p className="text-lg leading-relaxed">
                  OpenAlex does not support free text searches. Instead only boolean search is supported. For example:
                </p>

                <div className="bg-muted rounded-lg p-4 font-mono text-sm">
                  (parent OR family) AND (mental health) AND (intervention OR policy OR trial)
                </div>

                <p className="text-lg leading-relaxed">
                  In the future, Policy Atlas will support you constructing boolean queries from free text input.
                </p>


                <p className="text-lg leading-relaxed">
                  OpenAlex can also specify the minimum number of citations for the documents, to select higher impact papers.
                </p>


                {/* OpenAlex Video */}
                <div className="bg-muted rounded-lg p-4">
                  <div className="aspect-video w-full">
                                         <iframe
                       className="w-full h-full rounded border-0"
                       src="https://www.youtube.com/embed/JAnJtYU2ZV4?rel=0"
                       title="OpenAlex Search Tutorial"
                       allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                       allowFullScreen
                     ></iframe>
                  </div>
                </div>

              </div>

            <h4 className="text-xl font-semibold">Text summary</h4>
              <div className="space-y-4">
              <p className="text-lg leading-relaxed">
                Once you have your search results, you will be able to synthesise the text into a summary and visualise the results in various ways.
              </p>
              
              <p className="text-lg leading-relaxed">
                For now, you can generate a summary of the search results using the AI summary test feature. 
                Scroll down to the bottom of the page, to generate the summary (note: it might take a minute to generate the summary).
              </p>

              {/* AI Summary Video */}
              <div className="bg-muted rounded-lg p-4">
                <div className="aspect-video w-full">
                                     <iframe
                     className="w-full h-full rounded border-0"
                     src="https://www.youtube.com/embed/is2YLNkNa2A?rel=0"
                     title="AI Summary Tutorial"
                     allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                     allowFullScreen
                   ></iframe>
                </div>
              </div>

              <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                <p className="text-sm text-red-800 dark:text-red-200">
                  <strong>Warning:</strong> If you navigate away from the search page, your search results will be lost. 
                  We recommend downloading your results as a CSV file to preserve them for later analysis. We are working on a feature to save your search results.
                </p>
              </div>

              <div className="text-center">
                <Link href="/dashboard/search">
                  <Button className="flex items-center gap-2">
                    Try the Search feature
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
              </div>
            </div>
          </div>

          {/* Step 2: Synthesis */}
          <div className="space-y-6">
            <h3 className="text-2xl font-semibold flex items-center gap-2">
              <Brain className="h-6 w-6 text-green-600" />
              Step 2: Synthesis (Coming Soon)
            </h3>
            
            <div className="space-y-4">
              <p className="text-lg leading-relaxed">
                Once you have your search results, you will be able to synthesise the text into a more sophisticated summaries and visualise the results in various ways.
                This is currently under development.
              </p>
              
              
            </div>
         

            </div>
          </div>

          {/* Step 3: Simulation */}
          <div className="space-y-6">
            <h3 className="text-2xl font-semibold flex items-center gap-2">
              <Beaker className="h-6 w-6 text-purple-600" />
              Step 3: Simulation (Coming Soon)
            </h3>
            
            <div className="space-y-4">
            
            <p className="text-lg leading-relaxed">
              You will be able to create a network model (theory of change) where nodes are the intervention levers
              and outcomes reported in your search results. This will allow you to explore the relationships and underpinning evidence between different policy interventions.
              This feature is currently under development; see a demo with synthetic data below.
            </p>

              {/* Network Visualisation */}
              <div className="bg-muted rounded-lg p-4">
                <div className="aspect-video w-full">
                                     <iframe
                     className="w-full h-full rounded border-0"
                     src="https://www.youtube.com/embed/0-Y7nIU9jCk?rel=0"
                     title="Network Visualization Tutorial"
                     allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                     allowFullScreen
                   ></iframe>
                </div>
              </div>

              <p className="text-lg leading-relaxed">
                You will then be able to use the network visualisation to simulate the impact of different policy interventions.
                This will help you understand the potential trade-offs and unintended consequences of different policy interventions. Video below shows a demo with synthetic data.
              </p>

              {/* Simulation Video */}
              <div className="bg-muted rounded-lg p-4">
                <div className="aspect-video w-full">
                                     <iframe
                     className="w-full h-full rounded border-0"
                     src="https://www.youtube.com/embed/xDM1kdf_ioo?rel=0"
                     title="Policy Simulation Tutorial"
                     allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                     allowFullScreen
                   ></iframe>
                </div>
              </div>
            </div>
          </div>

          {/* Limitations Section */}
          <div className="space-y-4">
            <h4 className="text-xl font-semibold">Current Limitations</h4>
            <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
              <p className="text-sm">
                We are working with abstracts (summaries) of the documents. Full text support is coming soon.
              </p>
              <p className="text-sm mt-2">
                If you navigate away from the search page, your search results will be lost. We are working on a feature to save your search results.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Team Section */}
      <section id="team" className="space-y-6">

        <div className="text-center">
          <Link href="mailto:karlis.kanders@nesta.org.uk">
            <Button className="flex items-center gap-2 mx-auto">
              <Mail className="h-4 w-4" />
              Get in touch
            </Button>
          </Link>
        </div>
      </section>
    </div>
  )
} 