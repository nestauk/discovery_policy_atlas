'use client'

import { useMemo } from 'react'
import { Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Paper } from '@/types/search'
import { Check, X } from 'lucide-react'
import { Tooltip } from '@/components/ui/tooltip'
import { StarRating } from '@/components/ui/star-rating'
import { getEvidenceCategoryColors, getEvidenceCategoryShortName } from '@/lib/evidenceCategories'

interface PapersTableProps {
  papers: Paper[]
  showAdditionalColumns?: boolean
}

interface DataType extends Paper {
  key: string
  authorsDisplay: string
  topicsDisplay: string
  relevanceDisplay: string
}

export function PapersTable({ papers, showAdditionalColumns = false }: PapersTableProps) {
  // Transform papers data for the table
  const tableData: DataType[] = useMemo(() => {
    return papers.map((paper) => ({
      ...paper,
      key: paper.id,
      authorsDisplay: paper.authors?.join(', ') || 'Unknown',
      topicsDisplay: paper.topics?.slice(0, 2).join(', ') + (paper.topics && paper.topics.length > 2 ? ` +${paper.topics.length - 2} more` : ''),
      relevanceDisplay: paper.is_relevant ? 'Relevant' : 'Not Relevant'
    }))
  }, [papers])

  // Get extracted fields from the first paper (assuming all papers have the same extraction fields)
  const extractedFields = useMemo(() => {
    if (!papers.length) return []
    
    const firstPaper = papers[0]
    const fields = Object.keys(firstPaper).filter(key => 
      key.startsWith('extra_field_') && firstPaper[key as keyof Paper]
    )
    
    return fields.map((field, index) => ({
      key: field,
      title: `Extra Field ${index + 1}`,
      dataIndex: field,
      width: '10%',
      sorter: (a: DataType, b: DataType) => {
        const aValue = String(a[field as keyof DataType] || 'N/A')
        const bValue = String(b[field as keyof DataType] || 'N/A')
        return aValue.localeCompare(bValue)
      },
      render: (text: string, record: DataType) => (
        <div className="text-sm text-gray-700 whitespace-normal leading-tight" title={String(record[field as keyof DataType] || '')}>
          {String(record[field as keyof DataType] || 'N/A')}
        </div>
      ),
    }))
  }, [papers])

  // Build columns conditionally
  const baseColumns: ColumnsType<DataType> = [
    {
      title: 'Year',
      dataIndex: 'publication_year',
      key: 'publication_year',
      width: '6%',
      sorter: (a, b) => a.publication_year - b.publication_year,
      render: (text) => (
        <span>{text && text > 0 ? text : 'Unknown'}</span>
      ),
    },
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      width: '20%',
      render: (text, record) => {
        const maxLength = 80 // Truncate after 80 characters for titles
        // Prioritize landing_page_url, fallback to DOI, then overton_url
        const linkUrl = record.landing_page_url || (record.doi ? `${record.doi}` : record.overton_url)
        
        return linkUrl ? (
          <a 
            href={linkUrl} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 hover:underline"
            title={text} // Show full title on hover
          >
            {text.length > maxLength 
              ? `${text.substring(0, maxLength)}...` 
              : text
            }
          </a>
        ) : (
          <span title={text}>
            {text.length > maxLength 
              ? `${text.substring(0, maxLength)}...` 
              : text
            }
          </span>
        )
      },
      sorter: (a, b) => a.title.localeCompare(b.title),
    },
    {
      title: 'Top Line',
      dataIndex: 'top_line',
      key: 'top_line',
      width: '20%',
      render: (text, record) => (
        <div className="text-sm text-gray-700 whitespace-normal leading-tight">
          {record.top_line || 'No summary available'}
        </div>
      ),
    },
    {
      title: 'Country',
      dataIndex: 'source_country',
      key: 'source_country',
      width: '8%',
      sorter: (a, b) => (a.source_country || 'Academic').localeCompare(b.source_country || 'Academic'),
      render: (text) => (
        <span>{text || 'Academic'}</span>
      ),
    },
    {
      title: 'Authors',
      dataIndex: 'authorsDisplay',
      key: 'authors',
      width: '12%',
      sorter: (a, b) => a.authorsDisplay.localeCompare(b.authorsDisplay),
      render: (text, record) => {
        const authorsText = record.authors?.join(', ') || 'Unknown'
        const maxLength = 60 // Truncate after 60 characters
        
        return (
          <div className="text-sm text-gray-700 whitespace-normal leading-tight" title={authorsText}>
            {authorsText.length > maxLength 
              ? `${authorsText.substring(0, maxLength)}...` 
              : authorsText
            }
          </div>
        )
      },
    },
    {
      title: 'Citations',
      dataIndex: 'cited_by_count',
      key: 'cited_by_count',
      width: '6%',
      sorter: (a, b) => a.cited_by_count - b.cited_by_count,
      render: (text) => (
        <span className={text > 100 ? 'text-green-600 font-semibold' : ''}>
          {text}
        </span>
      ),
    },
    {
      title: 'Evidence Category',
      dataIndex: 'evidence_category',
      key: 'evidence_category_base',
      width: '10%',
      sorter: (a, b) => {
        const aRank = a.evidence_category_rank ?? 999
        const bRank = b.evidence_category_rank ?? 999
        return aRank - bRank
      },
      render: (_text, record) => {
        const category = record.evidence_category
        if (!category) {
          return <span className="text-gray-400 text-xs">-</span>
        }
        const colors = getEvidenceCategoryColors(category)
        const displayName = getEvidenceCategoryShortName(category)
        // Build tooltip: category name + reasoning (if available)
        const tooltipContent = record.evidence_category_reasoning
          ? `${category}\n\n${record.evidence_category_reasoning}`
          : category
        return (
          <Tooltip content={tooltipContent}>
            <span
              className="inline-block px-2 py-1 rounded text-xs font-medium cursor-help whitespace-normal leading-tight"
              style={{ backgroundColor: colors.bg, color: colors.text }}
            >
              {displayName}
            </span>
          </Tooltip>
        )
      },
    },
    {
      title: 'Evidence Strength',
      dataIndex: 'evidence_category',
      key: 'evidence_strength',
      width: '10%',
      sorter: (a, b) => (a.evidence_strength ?? 0) - (b.evidence_strength ?? 0),
      render: (_text, record) => {
        const score = record.evidence_strength
        const displayScore = score === 0 ? null : score ?? null
        const tooltip = record.evidence_strength_justification
        return (
          <StarRating
            stars={displayScore}
            size="sm"
            tooltip={tooltip}
          />
        )
      },
    },
    {
      title: 'Predicted Impact',
      dataIndex: 'predicted_impact',
      key: 'predicted_impact',
      width: '10%',
      sorter: (a, b) => (a.predicted_impact ?? 0) - (b.predicted_impact ?? 0),
      render: (text, record) => {
        return (
          <StarRating
            stars={record.predicted_impact}
            size="sm"
            tooltip={record.predicted_impact_justification}
          />
        )
      },
    },
    {
      title: 'Relevance',
      dataIndex: 'confidence',
      key: 'confidence',
      width: '8%',
      sorter: (a, b) => (a.confidence || 0) - (b.confidence || 0),
      defaultSortOrder: 'descend',
      render: (text, record) => {
        const relevanceContent = (
          <div className="flex items-center gap-1">
            <span>{record.confidence ? (record.confidence * 100).toFixed(1) : 'N/A'}</span>
            {record.is_relevant ? (
              <Check className="h-3 w-3 text-green-600" />
            ) : (
              <X className="h-3 w-3 text-red-500" />
            )}
          </div>
        )

        // Show tooltip with relevance_reason if available
        if (record.relevance_reason) {
          return (
            <Tooltip content={record.relevance_reason}>
              <div className="cursor-help">
                {relevanceContent}
              </div>
            </Tooltip>
          )
        }

        return relevanceContent
      },
    },
  ];

  // Conditional columns (Sample Size, Source, and Status)
  const conditionalColumns: ColumnsType<DataType> = showAdditionalColumns ? [
    {
      title: 'Sample Size',
      dataIndex: 'sample_size',
      key: 'sample_size',
      width: '8%',
      sorter: (a, b) => (a.sample_size || 0) - (b.sample_size || 0),
      render: (_text, record) => {
        const sampleSize = record.sample_size
        if (!sampleSize || sampleSize <= 0) {
          return <span className="text-gray-400 text-xs">-</span>
        }
        
        // Format large numbers with commas
        const formatted = sampleSize.toLocaleString()
        
        return (
          <span className="text-sm text-gray-700">
            {formatted}
          </span>
        )
      },
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      width: '6%',
      sorter: (a, b) => (a.source || '').localeCompare(b.source || ''),
      render: (_text, record) => {
        const source = record.source || 'unknown'
        let displayText = source
        
        if (source === 'openalex') {
          displayText = 'OpenAlex'
        } else if (source === 'overton') {
          displayText = 'Overton'
        }
        
        return (
          <span className="text-sm text-gray-700">
            {displayText}
          </span>
        )
      },
    },
    {
      title: 'Status',
      dataIndex: 'extraction_status',
      key: 'extraction_status',
      width: '8%',
      sorter: (a, b) => {
        const getStatusPriority = (status: string, textSource?: string) => {
          if (status === 'completed') return textSource === 'full_text' ? 3 : 2
          if (status === 'skipped') return 1
          return 0 // failed, not processed, unknown
        }

        const aPriority = getStatusPriority(a.extraction_status || 'unknown', a.text_source)
        const bPriority = getStatusPriority(b.extraction_status || 'unknown', b.text_source)
        return aPriority - bPriority
      },
      render: (_text, record) => {
        const status = record.extraction_status || 'unknown'
        const textSource = record.text_source
        
        let color = 'text-gray-500'
        let bgColor = 'bg-gray-100'
        let displayText = 'not processed'
        
        if (status === 'completed') {
          color = 'text-green-700'
          bgColor = 'bg-green-100'
          if (textSource === 'full_text') {
            displayText = 'completed: full-text'
          } else if (textSource === 'abstract') {
            displayText = 'completed: abstract'
          } else {
            displayText = 'completed'
          }
        } else if (status === 'failed') {
          color = 'text-gray-600'
          bgColor = 'bg-gray-100'
          displayText = 'not processed'
        } else if (status === 'skipped') {
          color = 'text-yellow-700'
          bgColor = 'bg-yellow-100'
          displayText = 'skipped'
        } else {
          // unknown or any other status
          displayText = 'not processed'
        }
        
        return (
          <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${color} ${bgColor}`}>
            {displayText}
          </span>
        )
      },
    },
  ] : [];

  // Combine all columns
  const columns: ColumnsType<DataType> = [
    ...baseColumns,
    ...conditionalColumns,
    // Add extracted fields as additional columns
    ...extractedFields
  ]

  return (
    <div className="space-y-4">
      
      <Table
        columns={columns}
        dataSource={tableData}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (total, range) => `${range[0]}-${range[1]} of ${total} items`,
        }}
        scroll={{ x: 1200 }}
        size="small"
        bordered
        rowClassName={(record) => record.is_relevant ? 'bg-green-50' : 'bg-white'}
        sortDirections={['descend', 'ascend']}
      />
    </div>
  )
} 
