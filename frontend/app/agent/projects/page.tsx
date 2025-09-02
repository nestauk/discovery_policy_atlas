'use client'

import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { FolderOpen, Plus, Search, Calendar, Edit, Trash2 } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { useAPI } from '@/lib/api'
import { useProjectStore, Project } from '@/lib/projectStore'

export default function ProjectsPage() {
  const router = useRouter()
  const { 
    getProjects, 
    createProject, 
    updateProject, 
    deleteProject 
  } = useAPI()
  const { 
    projects, 
    activeProject,
    setProjects, 
    addProject, 
    updateProject: updateProjectInStore,
    removeProject,
    setActiveProject,
    setLoading,
    isLoading,
    error,
    setError
  } = useProjectStore()

  const [newProjectDialog, setNewProjectDialog] = useState(false)
  const [editProjectDialog, setEditProjectDialog] = useState<Project | null>(null)
  const [projectForm, setProjectForm] = useState({ name: '', description: '' })

  const loadProjects = useCallback(async () => {
    try {
      setLoading(true)
      const response = await getProjects()
      setProjects(response.projects)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects')
    } finally {
      setLoading(false)
    }
  }, [getProjects, setLoading, setProjects, setError])

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  // loadProjects defined via useCallback above

  const handleCreateProject = async () => {
    if (!projectForm.name.trim()) return

    try {
      const newProject = await createProject(projectForm)
      addProject(newProject)
      setProjectForm({ name: '', description: '' })
      setNewProjectDialog(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
    }
  }

  const handleUpdateProject = async () => {
    if (!editProjectDialog || !projectForm.name.trim()) return

    try {
      const updatedProject = await updateProject(editProjectDialog.id, projectForm)
      updateProjectInStore(editProjectDialog.id, updatedProject)
      setProjectForm({ name: '', description: '' })
      setEditProjectDialog(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update project')
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    if (!confirm('Are you sure you want to delete this project? This will also delete all associated evidence.')) {
      return
    }

    try {
      await deleteProject(projectId)
      removeProject(projectId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project')
    }
  }

  const handleSelectProject = (project: Project) => {
    setActiveProject(project)
    router.push('/agent/results')
  }

  const openEditDialog = (project: Project) => {
    setProjectForm({ name: project.name, description: project.description || '' })
    setEditProjectDialog(project)
  }

  const openNewDialog = () => {
    setProjectForm({ name: '', description: '' })
    setNewProjectDialog(true)
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <h1 className="text-3xl font-bold text-slate-900">Projects</h1>
        {/* <p className="text-slate-600 mt-1">Manage your research projects and evidence synthesis</p> */}
        {error && (
          <div className="mt-2 text-red-600 text-sm">{error}</div>
        )}
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-semibold text-slate-900">Your Projects</h2>
            <Dialog open={newProjectDialog} onOpenChange={setNewProjectDialog}>
              <DialogTrigger asChild>
                <Button 
                  onClick={openNewDialog}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  New Project
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Create New Project</DialogTitle>
                </DialogHeader>
                <div className="space-y-4">
                  <div>
                    <label className="text-sm font-medium">Project Name</label>
                    <Input 
                      value={projectForm.name}
                      onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
                      placeholder="Enter project name"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Description (Optional)</label>
                    <Textarea 
                      value={projectForm.description}
                      onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                      placeholder="Brief description of the project"
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="outline" onClick={() => setNewProjectDialog(false)}>
                      Cancel
                    </Button>
                    <Button onClick={handleCreateProject}>
                      Create Project
                    </Button>
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="text-slate-500">Loading projects...</div>
            </div>
          ) : projects.length === 0 ? (
            <div className="text-center py-12">
              <div className="bg-slate-50 rounded-lg p-8">
                <FolderOpen className="h-12 w-12 text-slate-400 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Projects Yet</h3>
                <p className="text-slate-600 mb-6">
                  Create your first project to start organizing your research and evidence synthesis.
                </p>
                <Button 
                  onClick={openNewDialog}
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
                      <div className="flex items-center gap-2">
                        <FolderOpen className="h-5 w-5 text-blue-600" />
                        {project.name}
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
                    <p className="text-sm text-slate-600 mb-4">
                      {project.description || 'No description provided'}
                    </p>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Search className="h-3 w-3" />
                        {project.evidence_count} evidence
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {project.last_search_date 
                          ? new Date(project.last_search_date).toLocaleDateString()
                          : 'No searches yet'
                        }
                      </span>
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
                <DialogTitle>Edit Project</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="text-sm font-medium">Project Name</label>
                  <Input 
                    value={projectForm.name}
                    onChange={(e) => setProjectForm({ ...projectForm, name: e.target.value })}
                    placeholder="Enter project name"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Description (Optional)</label>
                  <Textarea 
                    value={projectForm.description}
                    onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                    placeholder="Brief description of the project"
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