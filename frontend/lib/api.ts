import { useAuth } from "@clerk/nextjs";
import { Project } from "./projectStore";
import { AnalysisProject } from "./analysisProjectStore";

export function useAPI() {
  const { getToken } = useAuth();
  
  const fetchWithAuth = async (url: string, options: RequestInit = {}, isStreaming: boolean = false) => {
    const token = await getToken();
    
    if (!token) {
      console.error("No authentication token available");
      throw new Error("No authentication token available - please sign in");
    }
    
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    // Remove trailing slash from baseUrl and leading slash from url if present
    const cleanBaseUrl = baseUrl.replace(/\/$/, '');
    const cleanUrl = url.replace(/^\//, '');
    const fullUrl = `${cleanBaseUrl}/${cleanUrl}`;
    
    if (process.env.NODE_ENV === 'development') {
      console.log(`API call: ${options.method || 'GET'} ${fullUrl}`);
    }
    
    // Don't set Content-Type for FormData - let browser set it with boundary
    const headers: Record<string, string> = {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
    };
    
    // Only set Content-Type to application/json if we're not sending FormData
    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }
    
    const response = await fetch(fullUrl, {
      ...options,
      headers,
    });
    
    if (!response.ok) {
      if (response.status === 401) {
        console.error("Authentication failed - token may be expired");
        throw new Error("Authentication failed - please refresh the page and sign in again");
      }
      throw new Error(`API call failed: ${response.status} ${response.statusText}`);
    }
    
    // For streaming responses, return the raw response
    // For regular API calls, parse as JSON
    return isStreaming ? response : response.json();
  };

  // Project API functions
  const getProjects = async (): Promise<{ projects: Project[], total: number }> => {
    return fetchWithAuth('projects/');
  };

  const createProject = async (project: { name: string; description?: string }): Promise<Project> => {
    return fetchWithAuth('projects/', {
      method: 'POST',
      body: JSON.stringify(project),
    });
  };

  const updateProject = async (projectId: string, updates: { name?: string; description?: string }): Promise<Project> => {
    return fetchWithAuth(`projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  };

  const deleteProject = async (projectId: string): Promise<void> => {
    return fetchWithAuth(`projects/${projectId}`, {
      method: 'DELETE',
    });
  };

  const getProject = async (projectId: string): Promise<Project> => {
    return fetchWithAuth(`projects/${projectId}`);
  };

  const getProjectDocuments = async (projectId: string): Promise<{ documents: Record<string, unknown>[], total: number }> => {
    return fetchWithAuth(`projects/${projectId}/documents`);
  };

  const updateProjectStats = async (projectId: string): Promise<{ message: string; evidence_count: number }> => {
    return fetchWithAuth(`projects/${projectId}/update-stats`, {
      method: 'POST',
    });
  };

  // Advanced RAG functions (insights are now automatically generated)
  const checkEvidenceStatus = async (projectId: string) => {
    return fetchWithAuth(`api/agent/evidence-status/${projectId}`);
  };

  // Analysis Project API functions
  const getAnalysisProjects = async (): Promise<{ projects: AnalysisProject[], total: number }> => {
    return fetchWithAuth('api/analysis-projects');
  };

  const createAnalysisProject = async (project: { title: string; description?: string; query?: string }) => {
    return fetchWithAuth('api/analysis-projects', {
      method: 'POST',
      body: JSON.stringify(project),
    });
  };

  const getAnalysisProject = async (projectId: string) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}`);
  };

  const updateAnalysisProject = async (projectId: string, updates: Partial<AnalysisProject>) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  };

  const deleteAnalysisProject = async (projectId: string): Promise<void> => {
    return fetchWithAuth(`api/analysis-projects/${projectId}`, {
      method: 'DELETE',
    });
  };

  const runAnalysisForProject = async (projectId: string, config: Record<string, unknown>) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/run-analysis`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  };

  const getDocumentExtraction = async (projectId: string, documentId: string) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/documents/${documentId}/extraction`);
  };

  const getProjectInterventions = async (projectId: string) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/interventions`);
  };
  
  return { 
    fetchWithAuth, 
    getProjects, 
    createProject, 
    updateProject, 
    deleteProject, 
    getProject, 
    getProjectDocuments,
    updateProjectStats,
    checkEvidenceStatus,
    // Analysis projects
    getAnalysisProjects,
    createAnalysisProject,
    getAnalysisProject,
    updateAnalysisProject,
    deleteAnalysisProject,
    runAnalysisForProject,
    getDocumentExtraction,
    getProjectInterventions
  };
} 