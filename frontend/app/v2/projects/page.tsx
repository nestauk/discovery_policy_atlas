'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FolderOpen, Plus, Search, Edit, Trash2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useAPI } from '@/lib/api'
import { useAnalysisProjectStore, AnalysisProject } from '@/lib/analysisProjectStore'

export default function ProjectsPage() {
  const router = useRouter()
  const { 
    getAnalysisProjects, 
    createAnalysisProject,
    updateAnalysisProject,
    deleteAnalysisProject
  } = useAPI()
  const { 
    projects, 
    activeProject,
    setProjects, 
    removeProject,
    setActiveProject,
    setLoading,
    isLoading,
    error,
    setError
  } = useAnalysisProjectStore()


  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [projectForm, setProjectForm] = useState({ title: '', description: '' })
  const [isCreating, setIsCreating] = useState(false)
  const [editProjectDialog, setEditProjectDialog] = useState<AnalysisProject | null>(null)
  const [editForm, setEditForm] = useState({ title: '', description: '' })

  useEffect(() => {
    loadProjects()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadProjects = async () => {
    try {
      setLoading(true)
      const response = await getAnalysisProjects()
      setProjects(response.projects)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analysis projects')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateProject = async () => {
    if (!projectForm.title.trim()) {
      setError('Title is required')
      return
    }


    try {
      setIsCreating(true)
      const newProject = await createAnalysisProject({
        title: projectForm.title.trim(),
        description: projectForm.description.trim() || undefined
      })
      
      // Add to store and set as active project
      setProjects([newProject, ...projects])
      setActiveProject(newProject)
      
      // Reset form and close dialog
      setProjectForm({ title: '', description: '' })
      setShowCreateDialog(false)
      
      // Redirect to search page
      router.push(`/v2/search`)
      
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create analysis project')
    } finally {
      setIsCreating(false)
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm('Are you sure you want to delete this analysis project? This will also delete all associated data.')) {
      return
    }

    try {
      await deleteAnalysisProject(projectId)
      removeProject(projectId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete analysis project')
    }
  }

  const handleSelectProject = (project: AnalysisProject) => {
    setActiveProject(project)
  }

  const openEditDialog = (project: AnalysisProject) => {
    setEditForm({ 
      title: project.title, 
      description: project.description || ''
    })
    setEditProjectDialog(project)
  }

  const handleUpdateProject = async () => {
    if (!editProjectDialog || !editForm.title.trim()) return

    try {
      const updatedProject = await updateAnalysisProject(editProjectDialog.id, {
        title: editForm.title.trim(),
        description: editForm.description.trim() || undefined
      })
      
      // Update in store
      setProjects(projects.map(p => p.id === editProjectDialog.id ? { ...p, ...updatedProject } : p))
      
      setEditForm({ title: '', description: '' })
      setEditProjectDialog(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update project')
    }
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <h1 className="text-3xl font-bold text-slate-900">Projects</h1>
        {error && (
          <div className="mt-2 text-red-600 text-sm">{error}</div>
        )}
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-semibold text-slate-900"></h2>
            <div className="flex gap-2">
              <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
                <DialogTrigger asChild>
                  <Button 
                    onClick={() => setShowCreateDialog(true)}
                    variant="outline"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Create Project
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Create Analysis Project</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4">
                    <div>
                      <label className="text-sm font-medium">Project Title</label>
                      <Input 
                        value={projectForm.title}
                        onChange={(e) => setProjectForm({ ...projectForm, title: e.target.value })}
                        placeholder="Enter a descriptive title for your project..."
                      />
                    </div>
                    <div>
                      <label className="text-sm font-medium">Description (Optional)</label>
                      <Textarea 
                        value={projectForm.description}
                        onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                        placeholder="Brief description of your research goals and topics..."
                        rows={3}
                      />
                    </div>

                    <div className="flex gap-2 justify-end">
                      <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
                        Cancel
                      </Button>
                      <Button onClick={handleCreateProject} disabled={isCreating}>
                        {isCreating ? 'Creating...' : 'Create Project'}
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>

            </div>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-slate-500">Loading projects...</div>
            </div>
          ) : projects.length === 0 ? (
            <div className="text-center py-12">
              <div className="bg-slate-50 rounded-lg p-8">
                <FolderOpen className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Analysis Projects Yet</h3>
                <p className="text-slate-600 mb-6">
                  Run your first analysis to create a project with structured policy research data and insights.
                </p>
                <Button 
                  onClick={() => setShowCreateDialog(true)}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  Create Your First Project
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {projects.map((project) => (
                <Card 
                  key={project.id} 
                  className={`border-slate-200 hover:border-blue-300 transition-colors cursor-pointer ${
                    activeProject?.id === project.id ? 'ring-2 ring-blue-500 border-blue-500' : ''
                  }`}
                  onClick={() => handleSelectProject(project)}
                >
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <FolderOpen className="h-5 w-5 text-blue-600 flex-shrink-0" />
                        <span className="truncate max-w-[180px]">{project.title}</span>
                      </div>
                      <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => openEditDialog(project)}
                        >
                          <Edit className="h-3 w-3" />
                        </Button>
                        <Button 
                          variant="ghost" 
                          size="sm"
                          onClick={() => handleDeleteProject(project.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="mb-4">
                      <p className="text-sm text-slate-600 mb-2">
                        {project.description || 'Analysis project ready for search queries'}
                      </p>
                      <div className="flex items-center justify-between text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                          <Search className="h-3 w-3" />
                          {project.total_references} total, {project.relevant_references} relevant
                        </span>
                        <span className={`px-2 py-1 rounded-md text-xs font-medium ${
                          project.status === 'completed' ? 'bg-green-100 text-green-800' :
                          project.status === 'running' ? 'bg-yellow-100 text-yellow-800' :
                          project.status === 'failed' ? 'bg-red-100 text-red-800' :
                          'bg-gray-100 text-gray-800'
                        }`}>
                          {project.status}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        {new Date(project.created_at).toLocaleDateString()}
                        {project.created_by_name && (
                          <span className="ml-2">• {project.created_by_name}</span>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Edit Project Dialog */}
          <Dialog open={!!editProjectDialog} onOpenChange={() => setEditProjectDialog(null)}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Edit Analysis Project</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Project Title</label>
                  <Input 
                    value={editForm.title}
                    onChange={(e) => setEditForm({ ...editForm, title: e.target.value })}
                    placeholder="Enter a descriptive title for your project..."
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Description (Optional)</label>
                  <Textarea 
                    value={editForm.description}
                    onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                    placeholder="Brief description of your research goals..."
                    rows={2}
                  />
                </div>
                
                <div className="flex gap-2 justify-end">
                  <Button variant="outline" onClick={() => setEditProjectDialog(null)}>
                    Cancel
                  </Button>
                  <Button onClick={handleUpdateProject}>
                    Update Project
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </main>
    </div>
  )
} 