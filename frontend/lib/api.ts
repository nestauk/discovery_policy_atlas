import { useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { AnalysisProject } from "./analysisProjectStore";

export const pingBackend = async (): Promise<boolean> => {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const cleanBaseUrl = baseUrl.replace(/\/$/, '');
  
  try {
    const response = await fetch(`${cleanBaseUrl}/health`, { 
      method: 'GET',
      cache: 'no-store'
    });
    return response.ok;
  } catch (error) {
    console.log('Backend ping failed (server may be waking up):', error);
    return false;
  }
};

// Standalone auth fetch to allow usage from non-React files (e.g., Zustand stores)
export const fetchWithAuthExternal = async (
  url: string,
  options: RequestInit = {},
  isStreaming: boolean = false
) => {
  let token: string | null = null;
  try {
    if (typeof window !== 'undefined' && (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } }).Clerk?.session) {
      const clerkWindow = window as unknown as { Clerk?: { session?: { getToken: () => Promise<string> } } }
      token = await clerkWindow.Clerk!.session!.getToken();
    }
  } catch (err) {
    console.error('Failed to get Clerk token from window:', err);
  }

  if (!token) {
    if (process.env.NODE_ENV === 'development') {
      console.warn("No authentication token available (external fetch)");
      return null;
    }
    console.error("No authentication token available (external fetch)");
    throw new Error("No authentication token available - please sign in");
  }

  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const cleanBaseUrl = baseUrl.replace(/\/$/, '');
  const cleanUrl = url.replace(/^\//, '');
  const fullUrl = `${cleanBaseUrl}/${cleanUrl}`;

  console.log(`API call (external): ${options.method || 'GET'} ${fullUrl}`);
  const headers = new Headers(options.headers as HeadersInit);
  headers.set('Authorization', `Bearer ${token}`);
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  let response: Response;
  try {
    response = await fetch(fullUrl, {
      ...options,
      headers,
    });
  } catch (fetchError) {
    console.error('Network fetch error (external):', fetchError);
    throw new Error(`Network error: ${fetchError instanceof Error ? fetchError.message : 'Unknown network error'}`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    console.error(`Response error body (external):`, errorText);
    if (response.status === 401) {
      console.error("Authentication failed - token may be expired");
      throw new Error("Authentication failed - please refresh the page and sign in again");
    }
    throw new Error(`API call failed: ${response.status} ${response.statusText} - ${errorText}`);
  }

  return isStreaming ? response : response.json();
};

export function useAPI() {
  const { getToken } = useAuth();
  
  const fetchWithAuth = useCallback(async (url: string, options: RequestInit = {}, isStreaming: boolean = false) => {
    const token = await getToken();
    
    if (!token) {
      if (process.env.NODE_ENV === 'development') {
        console.warn("No authentication token available");
        return null;
      }
      console.error("No authentication token available");
      throw new Error("No authentication token available - please sign in");
    }
    
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const cleanBaseUrl = baseUrl.replace(/\/$/, '');
    const cleanUrl = url.replace(/^\//, '');
    const fullUrl = `${cleanBaseUrl}/${cleanUrl}`;
    
    const headers = new Headers(options.headers as HeadersInit);
    headers.set('Authorization', `Bearer ${token}`);
    if (!(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    let response;
    try {
      response = await fetch(fullUrl, {
        ...options,
        headers,
      });
    } catch (fetchError) {
      console.error('Network fetch error:', fetchError);
      throw new Error(`Network error: ${fetchError instanceof Error ? fetchError.message : 'Unknown network error'}`);
    }
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Response error body:`, errorText);
      if (response.status === 401) {
        console.error("Authentication failed - token may be expired");
        throw new Error("Authentication failed - please refresh the page and sign in again");
      }
      throw new Error(`API call failed: ${response.status} ${response.statusText} - ${errorText}`);
    }
    
    return isStreaming ? response : response.json();
  }, [getToken]);

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

  const rerunSynthesisForProject = async (
    projectId: string,
    options: { force?: boolean; invalidate_previous?: boolean } = {}
  ) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/rerun-synthesis`, {
      method: 'POST',
      body: JSON.stringify({
        force: options.force ?? true,
        invalidate_previous: options.invalidate_previous ?? true,
      }),
    });
  };

  const getDocumentExtraction = async (projectId: string, documentId: string) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/documents/${documentId}/extraction`);
  };

  const getProjectInterventions = async (projectId: string) => {
    return fetchWithAuth(`api/analysis-projects/${projectId}/interventions`);
  };

  const generatePopulationOptions = async (researchQuestion: string): Promise<{ research_question: string; population_options: string[] }> => {
    return fetchWithAuth('api/analysis-projects/generate-population-options', {
      method: 'POST',
      body: JSON.stringify({ research_question: researchQuestion, max_options: 3 }),
    });
  };

  const generateOutcomeOptions = async (researchQuestion: string): Promise<{ research_question: string; outcome_options: string[] }> => {
    return fetchWithAuth('api/analysis-projects/generate-outcome-options', {
      method: 'POST',
      body: JSON.stringify({ research_question: researchQuestion, max_options: 3 }),
    });
  };

  const generateInnerSettingOptions = async (researchQuestion: string): Promise<{ research_question: string; inner_setting_options: string[] }> => {
    return fetchWithAuth('api/analysis-projects/generate-inner-setting-options', {
      method: 'POST',
      body: JSON.stringify({ research_question: researchQuestion, max_options: 5 }),
    });
  };

  return { 
    fetchWithAuth, 
    generatePopulationOptions,
    generateOutcomeOptions,
    generateInnerSettingOptions,
    // Analysis projects
    getAnalysisProjects,
    createAnalysisProject,
    getAnalysisProject,
    updateAnalysisProject,
    deleteAnalysisProject,
    runAnalysisForProject,
    rerunSynthesisForProject,
    getDocumentExtraction,
    getProjectInterventions,
  };
}