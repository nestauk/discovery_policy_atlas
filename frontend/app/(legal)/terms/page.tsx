import type { Metadata } from 'next'
import { LegalDocumentContent } from '../LegalDocumentContent'
import { readLegalDocument } from '../readLegalDocument'

export const metadata: Metadata = {
  title: 'Terms of Use | Policy Atlas',
}

export default function TermsPage() {
  const termsMarkdown = readLegalDocument('terms_of_use.md')

  return <LegalDocumentContent markdown={termsMarkdown} />
}
