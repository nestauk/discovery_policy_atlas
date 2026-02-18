import type { Metadata } from 'next'
import { LegalDocumentContent } from '../LegalDocumentContent'
import { readLegalDocument } from '../readLegalDocument'

export const metadata: Metadata = {
  title: 'Privacy Policy | Policy Atlas',
}

export default function PrivacyPage() {
  const privacyPolicyMarkdown = readLegalDocument('privacy_policy.md')

  return <LegalDocumentContent markdown={privacyPolicyMarkdown} />
}
