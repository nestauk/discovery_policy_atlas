'use client'

import { useState, useEffect, useCallback } from 'react'
import { useUser } from '@clerk/nextjs'
import { Select, Button, Modal, Input, message } from 'antd'
import { SaveOutlined } from '@ant-design/icons'
import { useAPI } from '@/lib/api'
import { SearchParams } from '@/types/search'


interface Project {
  id: string
  name: string
  description: string | null
  query: string
  filters: SearchParams
  created_at: string
}

interface ProjectSelectorProps {
  currentQuery: string
  currentFilters: SearchParams
  onProjectSelect: (query: string, filters: SearchParams, projectId: string) => void
}

export function ProjectSelector({
  currentQuery,
  currentFilters,
  onProjectSelect,
}: ProjectSelectorProps) {
  const { user } = useUser()
  const [projects, setProjects] = useState<Project[]>([])
  const [isModalVisible, setIsModalVisible] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [existingProject, setExistingProject] = useState<Project | null>(null)
  const { fetchWithAuth } = useAPI()

  const fetchProjects = useCallback(async () => {
    if (!user?.id) {
      console.log('No user ID available')
      return
    }

    try {
      console.log('Fetching projects...')
      const data = await fetchWithAuth(`/api/projects/?clerk_user_id=${user.id}`)
      console.log('Projects fetched:', data)
      setProjects(data)
    } catch (error) {
      console.error('Error fetching projects:', error)
      message.error('Failed to load saved projects')
    }
  }, [user?.id, fetchWithAuth])

  useEffect(() => {
    if (user?.id) {
      console.log('User ID available, fetching projects...')
      fetchProjects()
    } else {
      console.log('No user ID available')
    }
  }, [user?.id, fetchProjects])

  const handleSave = async () => {
    if (!user?.id) {
      message.error('Please sign in to save projects')
      return
    }

    if (!projectName.trim()) {
      message.error('Please enter a project name')
      return
    }

    try {
      console.log('Saving project:', { name: projectName, query: currentQuery, filters: currentFilters })
      const data = await fetchWithAuth(`/api/projects/?clerk_user_id=${user.id}`, {
        method: 'POST',
        body: JSON.stringify({
          name: projectName,
          query: currentQuery,
          filters: currentFilters,
        }),
      })

      console.log('Project saved successfully:', data)
      message.success('Project saved successfully')
      setIsModalVisible(false)
      setProjectName('')
      fetchProjects()
    } catch (error) {
      console.error('Error saving project:', error)
      message.error('Failed to save project')
    }
  }

  const handleProjectSelect = async (projectId: string) => {
    if (!user?.id) {
      message.error('Please sign in to load projects')
      return
    }

    try {
      console.log('Selecting project:', projectId)
      const project = await fetchWithAuth(`/api/projects/${projectId}?clerk_user_id=${user.id}`)
      console.log('Project loaded:', {
        id: project.id,
        name: project.name,
        query: project.query,
        filters: project.filters,
        created_at: project.created_at
      })
      
      // Call the parent's onProjectSelect with the project data
      onProjectSelect(project.query, project.filters, project.id)
    } catch (error) {
      console.error('Error loading project:', error)
      message.error('Failed to load project')
    }
  }

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Select
          style={{ width: '100%' }}
          placeholder="Select a saved project"
          onChange={handleProjectSelect}
          options={projects.map(project => ({
            label: project.name,
            value: project.id,
          }))}
        />
        <Button
          icon={<SaveOutlined />}
          onClick={() => setIsModalVisible(true)}
        />
      </div>

      <Modal
        title="Save Project"
        open={isModalVisible}
        onOk={handleSave}
        onCancel={() => {
          setIsModalVisible(false)
          setProjectName('')
          setExistingProject(null)
        }}
      >
        <Input
          placeholder="Enter project name"
          value={projectName}
          onChange={e => setProjectName(e.target.value)}
        />
        {existingProject && (
          <p className="text-yellow-600 mt-2">
            A project with this name already exists. Saving will overwrite it.
          </p>
        )}
      </Modal>
    </div>
  )
} 