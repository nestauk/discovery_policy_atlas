'use client'

import { useMemo } from 'react'
import { Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { Paper } from '@/types/search'
import { Check, X } from 'lucide-react'

interface PapersTableProps {
  papers: Paper[]
}

interface DataType extends Paper {
  key: string
  authorsDisplay: string
  topicsDisplay: string
  relevanceDisplay: string
}

export function PapersTable({ papers }: PapersTableProps) {
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



  // Combine base columns with extracted field columns
  const columns: ColumnsType<DataType> = [
    {
      title: 'Year',
      dataIndex: 'publication_year',
      key: 'publication_year',
      width: '8%',
      sorter: (a, b) => a.publication_year - b.publication_year,
      render: (text) => (
        <span>{text && text > 0 ? text : 'Unknown'}</span>
      ),
    },
    {
      title: 'Title',
      dataIndex: 'title',
      key: 'title',
      width: '25%',
      render: (text, record) => {
        const maxLength = 100 // Truncate after 100 characters for titles
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
      width: '78%',
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
      width: '12%',
      sorter: (a, b) => (a.source_country || 'Academic').localeCompare(b.source_country || 'Academic'),
      render: (text) => (
        <span>{text || 'Academic'}</span>
      ),
    },
    {
      title: 'Authors',
      dataIndex: 'authorsDisplay',
      key: 'authors',
      width: '20%',
      sorter: (a, b) => a.authorsDisplay.localeCompare(b.authorsDisplay),
      render: (text, record) => {
        const authorsText = record.authors?.join(', ') || 'Unknown'
        const maxLength = 80 // Truncate after 80 characters
        
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
      width: '8%',
      sorter: (a, b) => a.cited_by_count - b.cited_by_count,
      render: (text) => (
        <span className={text > 100 ? 'text-green-600 font-semibold' : ''}>
          {text}
        </span>
      ),
    },
    {
      title: 'Relevance',
      dataIndex: 'confidence',
      key: 'confidence',
      width: '10%',
      sorter: (a, b) => (a.confidence || 0) - (b.confidence || 0),
      render: (text, record) => (
        <div className="flex items-center gap-1">
          <span>{record.confidence ? (record.confidence * 100).toFixed(1) : 'N/A'}</span>
          {record.is_relevant ? (
            <Check className="h-3 w-3 text-green-600" />
          ) : (
            <X className="h-3 w-3 text-red-500" />
          )}
        </div>
      ),
    },
    {
      title: 'Full Text',
      dataIndex: 'full_text_available',
      key: 'full_text_available',
      width: '6%',
      sorter: (a, b) => {
        const aVal = a.full_text_available === true ? 1 : a.full_text_available === false ? 0 : -1
        const bVal = b.full_text_available === true ? 1 : b.full_text_available === false ? 0 : -1
        return aVal - bVal
      },
      render: (text, record) => {
        if (record.full_text_available === true) {
          return <span className="text-green-600 font-semibold">✓</span>
        } else if (record.full_text_available === false) {
          return <span className="text-red-600">✗</span>
        } else {
          return <span className="text-gray-400">?</span>
        }
      },
    },
    {
      title: 'Status',
      dataIndex: 'extraction_status',
      key: 'extraction_status',
      width: '8%',
      sorter: (a, b) => (a.extraction_status || 'unknown').localeCompare(b.extraction_status || 'unknown'),
      render: (text, record) => {
        const status = record.extraction_status || 'unknown'
        let color = 'text-gray-500'
        let bgColor = 'bg-gray-100'
        
        if (status === 'success') {
          color = 'text-green-700'
          bgColor = 'bg-green-100'
        } else if (status === 'failed') {
          color = 'text-red-700'
          bgColor = 'bg-red-100'
        } else if (status === 'skipped') {
          color = 'text-yellow-700'
          bgColor = 'bg-yellow-100'
        }
        
        return (
          <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${color} ${bgColor}`}>
            {status}
          </span>
        )
      },
    },
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
      />
    </div>
  )
} 