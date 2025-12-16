'use client'

import { useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { ChevronDown, ChevronRight, HelpCircle, Star } from 'lucide-react'

interface FAQItem {
  id: string
  question: string
  answer: string | React.ReactNode
}

const StarRating = ({ rating }: { rating: number }) => (
  <div className="flex items-center gap-1">
    {[...Array(5)].map((_, i) => (
      <Star 
        key={i} 
        className={`h-4 w-4 ${i < rating ? 'text-yellow-400 fill-current' : 'text-slate-300'}`} 
      />
    ))}
    <span className="ml-2 text-sm font-medium text-slate-600">{rating}/5</span>
  </div>
)

const EvidenceStrengthFAQ = () => (
  <div className="space-y-4">
    <p className="text-slate-700 leading-relaxed">
      Evidence strength is rated by a large language model on a 5-star scale based on methodological quality, reliability, and robustness. 
      We begin at 5 stars and discount by 1 for each unmet major criterion. If the description of the study is not clear, we set the rating to 0
      and add an evidence gap explanation.
      <br />
      <br />
      The approach is still in development and we are working to improve it.
    </p>
    
    <div className="space-y-3">
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={5} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">RCT or strong quasi-experimental design</p>
          <p className="text-sm text-slate-600">Large sample, validated measures, sufficient mitigation of confounders, strong statistical significance, large effect size</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={4} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">RCT/quasi with moderate/large sample</p>
          <p className="text-sm text-slate-600">Partial mitigation of confounders, validated methods, medium or smaller effect sizes</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={3} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">RCT/quasi with moderate sample</p>
          <p className="text-sm text-slate-600">Partial mitigation, methods not fully validated; or small sample but some strong controls</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={2} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Weak quasi-experimental or small RCT</p>
          <p className="text-sm text-slate-600">Limited controls, unvalidated methods, limited statistical power</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={1} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Anecdotal evidence or uncontrolled pre-post</p>
          <p className="text-sm text-slate-600">Insufficient mitigation, small/biased sample, no statistical significance despite correlation</p>
        </div>
      </div>
    </div>

  </div>
)

const ImpactAssessmentFAQ = () => (
  <div className="space-y-4">
    <p className="text-slate-700 leading-relaxed">
      Predicted impact assessment is assessed by a large language model, evaluating the likelihood of scaling outcomes beyond the study context, 
    using a 5-star scale. We assess the main intervention studied in each paper, not secondary or control conditions.
    <br />
    <br />
    The approach is still in development and we are working to improve it.
    </p>

    
    <div className="space-y-3">
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={5} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Strong causal evidence with large effects</p>
          <p className="text-sm text-slate-600">Replicated or validated, generalizable to population, mitigation of confounders, strong evidence of external validity</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={4} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Adequate causal link with medium effect size</p>
          <p className="text-sm text-slate-600">Good but partial mitigation, some generalizability concerns, but broadly reliable</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={3} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Smaller effect size or context-limited</p>
          <p className="text-sm text-slate-600">Moderate sample, some threats to generalizability, still a plausible impact</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={2} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Uncertain or inconsistent evidence</p>
          <p className="text-sm text-slate-600">Weak causal link, effects fragile or highly context-specific</p>
        </div>
      </div>
      
      <div className="flex items-start gap-3 p-4 bg-slate-50 rounded-lg border border-slate-200">
        <StarRating rating={1} />
        <div className="flex-1">
          <p className="font-medium text-slate-900 mb-1">Anecdotal or speculative impact</p>
          <p className="text-sm text-slate-600">Minimal empirical support</p>
        </div>
      </div>
    </div>
  </div>
)

const faqItems: FAQItem[] = [
  {
    id: '1',
    question: 'How do I start a new analysis project?',
    answer: 'To create a new analysis project, go to the Search page and enter your research query. The system will automatically create a project and begin searching for relevant evidence. You can then review the results and refine your search as needed.'
  },
  {
    id: '2',
    question: 'How is evidence strength assessed?',
    answer: <EvidenceStrengthFAQ />
  },
  {
    id: '3',
    question: 'How is predicted impact assessment assessed?',
    answer: <ImpactAssessmentFAQ />
  }
]

export default function FAQPage() {
  const [openItems, setOpenItems] = useState<string[]>([])

  const toggleItem = (id: string) => {
    setOpenItems(prev => 
      prev.includes(id) 
        ? prev.filter(item => item !== id)
        : [...prev, id]
    )
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Frequently Asked Questions</h1>
          </div>
        </div>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="space-y-4">
            {faqItems.map((item) => (
              <Card key={item.id} className="border-slate-200 hover:border-blue-300 transition-colors">
                <CardContent className="p-0">
                  <button
                    onClick={() => toggleItem(item.id)}
                    className="w-full p-6 text-left flex items-center justify-between hover:bg-slate-50 transition-colors"
                  >
                    <h3 className="text-lg font-semibold text-slate-900 pr-4">
                      {item.question}
                    </h3>
                    {openItems.includes(item.id) ? (
                      <ChevronDown className="h-5 w-5 text-slate-500 flex-shrink-0" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-slate-500 flex-shrink-0" />
                    )}
                  </button>
                  
                  {openItems.includes(item.id) && (
                    <div className="px-6 pb-6 pt-0">
                      <div className="border-t border-slate-200 pt-4">
                        {typeof item.answer === 'string' ? (
                          <p className="text-slate-700 leading-relaxed">
                            {item.answer}
                          </p>
                        ) : (
                          item.answer
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-12 text-center">
            <div className="bg-slate-50 rounded-lg p-8">
              <HelpCircle className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">Still have questions?</h3>
              <p className="text-slate-600 mb-6">
                Contact us for assistance.
              </p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}