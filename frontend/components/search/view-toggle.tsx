'use client'

import { Button } from '@/components/ui/button'
import { Table, List } from 'lucide-react'

interface ViewToggleProps {
  currentView: 'cards' | 'table'
  onViewChange: (view: 'cards' | 'table') => void
}

export function ViewToggle({ currentView, onViewChange }: ViewToggleProps) {
  return (
    <div className="flex items-center px-4">
      <span className="text-sm text-muted-foreground mr-2"></span>
      <Button
        variant={currentView === 'cards' ? 'default' : 'outline'}
        size="sm"
        onClick={() => onViewChange('cards')}
        className="flex items-center space-x-1"
      >
        <List className="h-4 w-4" />
        <span className="text-current">Cards</span>
      </Button>
      <div className="w-2"></div>
      <Button
        variant={currentView === 'table' ? 'default' : 'outline'}
        size="sm"
        onClick={() => onViewChange('table')}
        className="flex items-center space-x-1"
      >
        <Table className="h-4 w-4" />
        <span className="text-current">Table</span>
      </Button>
    </div>
  )
} 