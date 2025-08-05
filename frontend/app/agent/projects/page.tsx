'use client'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FolderOpen, Plus, Search, Calendar } from 'lucide-react'
import { useRouter } from 'next/navigation'

export default function ProjectsPage() {
  const router = useRouter()

  return (
    <div className="flex-1 flex flex-col">
      <div className="border-b border-slate-200 bg-white px-8 py-6">
        <h1 className="text-2xl font-bold text-slate-900">Projects</h1>
        <p className="text-slate-600 mt-1">Manage your research projects and evidence synthesis</p>
      </div>

      <main className="flex-1 p-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xl font-semibold text-slate-900">Your Projects</h2>
            <Button 
              onClick={() => router.push('/agent')}
              className="bg-blue-600 hover:bg-blue-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              New Project
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Example Project Cards */}
            <Card className="border-slate-200 hover:border-blue-300 transition-colors cursor-pointer">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-blue-600" />
                  Youth Vaping Policy
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-600 mb-4">
                  Research on the health impacts of vaping among young people and policy recommendations.
                </p>
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <Search className="h-3 w-3" />
                    3 searches
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Updated 2 days ago
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200 hover:border-blue-300 transition-colors cursor-pointer">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-green-600" />
                  Climate Policy Analysis
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-600 mb-4">
                  Evidence synthesis for climate change mitigation policies and their effectiveness.
                </p>
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <Search className="h-3 w-3" />
                    7 searches
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Updated 1 week ago
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card className="border-slate-200 hover:border-blue-300 transition-colors cursor-pointer">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FolderOpen className="h-5 w-5 text-purple-600" />
                  Education Technology
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-slate-600 mb-4">
                  Research on the impact of digital tools in educational settings.
                </p>
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span className="flex items-center gap-1">
                    <Search className="h-3 w-3" />
                    2 searches
                  </span>
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    Updated 3 days ago
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* <div className="mt-12 text-center">
            <div className="bg-slate-50 rounded-lg p-8">
              <FolderOpen className="h-12 w-12 text-slate-400 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-900 mb-2">No Projects Yet</h3>
              <p className="text-slate-600 mb-6">
                Create your first project to start organizing your research and evidence synthesis.
              </p>
              <Button 
                onClick={() => router.push('/agent')}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Plus className="h-4 w-4 mr-2" />
                Create Your First Project
              </Button>
            </div>
          </div> */}
        </div>
      </main>
    </div>
  )
} 