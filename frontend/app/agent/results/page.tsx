'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  FileText, 
  Download, 
  Search, 
  TrendingUp,
  Globe,
  Shield,
  Lightbulb,
  BookOpen,
  Star,
  ArrowRight,
  ChevronDown
} from 'lucide-react'

// Mock data for the results
const mockResults = {
  sourcesFound: 3,
  confidence: 'High',
  quality: 'Peer-reviewed',
  executiveBrief: {
    text: 'Recent studies and reports have highlighted significant health risks associated with both vaping and smoking among youth. While vaping is often perceived as a safer alternative to smoking, evidence indicates that it poses substantial health threats, including nicotine addiction, respiratory issues, and potential progression to traditional cigarette use. This underscores the need for comprehensive public health strategies to mitigate these risks.',
    geographicCoverage: 'Global scope with emphasis on North America and Europe'
  },
  keyInsights: [
    'Nicotine exposure from vaping is comparable to that from smoking, leading to similar addiction risks among adolescents.',
    'Vaping is associated with respiratory problems, including asthma exacerbations and lung injuries.',
    'Youth vaping may serve as a gateway to traditional cigarette smoking, increasing the likelihood of dual use.',
    'Environmental concerns arise from the disposal of single-use vapes, contributing to electronic waste and pollution.'
  ],
  evidence: [
    {
      title: 'Adolescent E-cigarette Use and Subsequent Tobacco Product Use',
      authors: 'Johnson et al., 2023',
      journal: 'Journal of Health Policy',
      type: 'Peer-reviewed study',
      relevance: 94,
      keyFinding: 'Youth who used e-cigarettes were 3.6 times more likely to use conventional tobacco products within 12 months.',
      methodology: 'Longitudinal cohort study following 2,500 adolescents over 24 months'
    },
    {
      title: 'Respiratory Health Effects of E-cigarette Use Among Young Adults',
      authors: 'Chen & Williams, 2023',
      journal: 'Respiratory Medicine International',
      type: 'Meta-analysis',
      relevance: 91,
      keyFinding: 'E-cigarette use associated with 40% increased risk of respiratory symptoms compared to non-users.',
      methodology: 'Systematic review and meta-analysis of 15 studies (n=12,450)'
    },
    {
      title: 'Global Policy Responses to Youth Vaping: A Comparative Analysis',
      authors: 'Rodriguez et al., 2023',
      journal: 'International Policy Review',
      type: 'Policy analysis',
      relevance: 87,
      keyFinding: 'Countries with comprehensive vaping restrictions saw 35% reduction in youth initiation rates.',
      methodology: 'Cross-national analysis of policy implementations across 18 countries'
    }
  ]
}

export default function ResultsPage() {
  const [activeTab, setActiveTab] = useState('summary')
  const [expandedRecommendation, setExpandedRecommendation] = useState<number | null>(null)
  const router = useRouter()
  const urlSearchParams = useSearchParams()

  useEffect(() => {
    // URL params are available via urlSearchParams if needed
  }, [urlSearchParams])

  const handleNewSearch = () => {
    router.push('/agent')
  }

  const toggleRecommendation = (index: number) => {
    setExpandedRecommendation(expandedRecommendation === index ? null : index)
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Header */}
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center justify-between">
          <div className="flex flex-col">
            <h1 className="text-3xl font-bold text-slate-900">Search results</h1>
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="bg-green-100 text-green-700">
                {mockResults.sourcesFound} Sources Found
              </Badge>
              <Badge variant="secondary" className="bg-yellow-100 text-yellow-700">
                {mockResults.confidence}
              </Badge>
              <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                {mockResults.quality}
              </Badge>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm">
              <Download className="h-4 w-4 mr-2" />
              Export Report
            </Button>
            <Button onClick={handleNewSearch} className="bg-blue-600 hover:bg-blue-700">
              <Search className="h-4 w-4 mr-2" />
              New Search
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 bg-slate-50">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <div className="px-6 pt-4">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="summary" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                Summary
              </TabsTrigger>
              <TabsTrigger value="evidence" className="flex items-center gap-2">
                <BookOpen className="h-4 w-4" />
                Evidence
              </TabsTrigger>
              <TabsTrigger value="policy" className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Policy
              </TabsTrigger>
              <TabsTrigger value="generator" className="flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Generator
              </TabsTrigger>
              <TabsTrigger value="insights" className="flex items-center gap-2">
                <Lightbulb className="h-4 w-4" />
                Insights
              </TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-auto">
            <TabsContent value="summary" className="p-6 m-0">
              <div className="w-full">
                {/* Executive Brief */}
                <Card className="mb-8">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5" />
                      Executive Brief
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-slate-700 leading-relaxed mb-4">
                      {mockResults.executiveBrief.text}
                    </p>
                    <div className="flex items-center gap-2 text-sm text-slate-600">
                      <Globe className="h-4 w-4" />
                      <span>Geographic Coverage:</span>
                      <span className="font-medium">{mockResults.executiveBrief.geographicCoverage}</span>
                    </div>
                  </CardContent>
                </Card>

                {/* Key Insights */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <TrendingUp className="h-5 w-5" />
                      Key Insights
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      {mockResults.keyInsights.map((insight, index) => (
                        <div key={index} className="flex items-start gap-3">
                          <div className="w-6 h-6 bg-orange-100 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                            <Star className="h-3 w-3 text-orange-600" />
                          </div>
                          <p className="text-slate-700 leading-relaxed">{insight}</p>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            <TabsContent value="evidence" className="p-6 m-0">
              <div className="w-full">
                <div className="space-y-6">
                  {mockResults.evidence.map((study, index) => (
                    <Card key={index} className="border-slate-200">
                      <CardContent className="p-6">
                        <div className="flex justify-between items-start mb-4">
                          <div className="flex-1">
                            <h3 className="font-semibold text-lg text-slate-900 mb-2">
                              {study.title}
                            </h3>
                            <p className="text-slate-600 text-sm mb-2">
                              {study.authors} • {study.journal}
                            </p>
                            <Badge variant="outline" className="text-xs">
                              {study.type}
                            </Badge>
                          </div>
                          <div className="text-right">
                            <div className="text-sm font-medium text-slate-900">
                              {study.relevance}% Relevance
                            </div>
                            <Progress value={study.relevance} className="w-20 mt-1" />
                          </div>
                        </div>
                        
                        <div className="bg-slate-50 rounded-lg p-4 mb-4">
                          <h4 className="font-medium text-slate-900 mb-2">Key Finding</h4>
                          <p className="text-slate-700 text-sm leading-relaxed">
                            {study.keyFinding}
                          </p>
                        </div>

                        <div>
                          <h4 className="font-medium text-slate-900 mb-2">Methodology</h4>
                          <p className="text-slate-600 text-sm">
                            {study.methodology}
                          </p>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="policy" className="p-6 m-0">
              <div className="w-full max-w-4xl mx-auto">
                {/* Policy Recommendations Section */}
                <div className="mb-8">
                  <div className="space-y-3">
                    {[
                      "Implement stricter regulations on youth-targeted vaping products.",
                      "Consider public health impacts in product approval processes.",
                      "Enhance enforcement against illegal vape products to protect youth.",
                      "Develop comprehensive public health campaigns to educate about vaping risks.",
                      "Collaborate with international bodies to harmonize vaping product regulations."
                    ].map((recommendation, index) => (
                      <Card 
                        key={index} 
                        className="border border-slate-200 bg-white cursor-pointer hover:shadow-md transition-shadow"
                        onClick={() => toggleRecommendation(index)}
                      >
                        <CardContent className="p-4">
                          <div className="flex items-center gap-4">
                            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center flex-shrink-0">
                              <span className="text-white font-semibold text-sm">
                                {index + 1}
                              </span>
                            </div>
                            <p className="text-slate-900 flex-1 leading-tight">
                              {recommendation}
                            </p>
                            <div 
                              className="flex-shrink-0 cursor-pointer"
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleRecommendation(index)
                              }}
                            >
                              {expandedRecommendation === index ? (
                                <ChevronDown className="h-4 w-4 text-slate-400" />
                              ) : (
                                <ArrowRight className="h-4 w-4 text-slate-400" />
                              )}
                            </div>
                          </div>
                          
                          {/* Expanded Content */}
                          {expandedRecommendation === index && (
                            <div className="mt-4 pt-4 border-t border-slate-200">
                              <div className="space-y-4">
                                {/* Best Evidence */}
                                <div>
                                  <h4 className="font-medium text-slate-900 mb-2">Evidence</h4>
                                  <div className="bg-slate-50 rounded-lg p-3">
                                    <p className="text-sm text-slate-700 mb-2">
                                      {index === 0 && '"Countries with comprehensive vaping restrictions saw 35% reduction in youth initiation rates."'}
                                      {index === 1 && '"Public health impact assessments in product approval processes reduced harmful product introductions by 42%."'}
                                      {index === 2 && '"Enhanced enforcement programs resulted in 60% reduction in illegal vape product availability in schools."'}
                                      {index === 3 && '"Comprehensive public health campaigns led to 28% decrease in youth vaping initiation rates."'}
                                      {index === 4 && '"International harmonization of vaping regulations reduced cross-border illicit trade by 45%."'}
                                    </p>
                                    <div className="flex items-center gap-2 text-xs text-slate-600">
                                      <span className="font-medium">Source:</span>
                                      <a 
                                        href="https://openalex.org/placeholder" 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="text-blue-600 hover:text-blue-800 underline"
                                      >
                                        {index === 0 && "Rodriguez et al., 2023 - International Policy Review"}
                                        {index === 1 && "Chen & Williams, 2023 - Public Health Policy"}
                                        {index === 2 && "Thompson et al., 2023 - Law Enforcement Studies"}
                                        {index === 3 && "Davis & Kim, 2023 - Health Communication Research"}
                                        {index === 4 && "Global Policy Institute, 2023 - International Relations"}
                                      </a>
                                    </div>
                                  </div>
                                </div>
                                
                                {/* Implementation Guidance */}
                                <div>
                                  <h4 className="font-medium text-slate-900 mb-2">Implementation Guidance</h4>
                                  <ul className="space-y-2 text-sm text-slate-700">
                                    {index === 0 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish age verification systems for online and retail sales</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement flavor restrictions targeting youth appeal</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Set minimum price requirements to reduce affordability</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 1 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Require health impact assessments for all new vaping products</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish independent review panels with public health expertise</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement post-market surveillance requirements</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 2 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Increase penalties for illegal vape product distribution</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish dedicated enforcement units with specialized training</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Implement anonymous reporting systems for illegal sales</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 3 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Develop age-appropriate educational materials for schools</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Partner with healthcare providers for community outreach</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Utilize social media platforms for targeted messaging</span>
                                        </li>
                                      </>
                                    )}
                                    {index === 4 && (
                                      <>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Establish bilateral agreements with neighboring countries</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Participate in international vaping policy forums</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                          <span className="text-blue-600 flex-shrink-0 mt-0.5">•</span>
                                          <span>Share best practices and enforcement strategies globally</span>
                                        </li>
                                      </>
                                    )}
                                  </ul>
                                </div>
                              </div>
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </div>


              </div>
            </TabsContent>

            <TabsContent value="generator" className="p-6 m-0">
              <div className="flex items-center justify-center h-96">
                <div className="text-center">
                  <Shield className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">Report Generator</h3>
                  <p className="text-slate-600">Automated report generation coming soon</p>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="insights" className="p-6 m-0">
              <div className="flex items-center justify-center h-96">
                <div className="text-center">
                  <Lightbulb className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-slate-900 mb-2">Advanced Insights</h3>
                  <p className="text-slate-600">AI-powered insights and analytics coming soon</p>
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  )
}