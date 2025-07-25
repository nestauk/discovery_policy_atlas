'use client'

import { useState } from 'react'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@clerk/nextjs'

interface DownloadButtonProps {
  downloadKey?: string
  disabled?: boolean
  className?: string
}

export function DownloadButton({ downloadKey, disabled, className }: DownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false)
  const { getToken } = useAuth()

  const handleDownload = async () => {
    if (!downloadKey) {
      console.error('No download available')
      return
    }

    setIsDownloading(true)
    
    try {
      // Get auth token and make authenticated request
      const token = await getToken()
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const cleanBaseUrl = baseUrl.replace(/\/$/, '')
      
      const downloadResponse = await fetch(`${cleanBaseUrl}/api/download/${downloadKey}`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'text/csv',
        },
      })
      
      if (!downloadResponse.ok) {
        if (downloadResponse.status === 404) {
          console.error('Download link has expired')
          alert('Download link has expired')
        } else {
          console.error('Failed to download file')
          alert('Failed to download file')
        }
        return
      }

      // Get filename from response headers
      const contentDisposition = downloadResponse.headers.get('Content-Disposition')
      let filename = 'search_results.csv'
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename=(.+)/)
        if (filenameMatch) {
          filename = filenameMatch[1]
        }
      }

      // Create blob and download
      const blob = await downloadResponse.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      console.log('Download started successfully')
    } catch (error) {
      console.error('Download error:', error)
      alert('Failed to download file')
    } finally {
      setIsDownloading(false)
    }
  }

  if (!downloadKey) {
    return null
  }

  return (
    <Button
      onClick={handleDownload}
      disabled={disabled || isDownloading}
      variant="outline"
      className={className}
      data-download-key={downloadKey}
    >
      <Download className="h-4 w-4 mr-2" />
      {isDownloading ? 'Downloading...' : 'Download CSV'}
    </Button>
  )
} 