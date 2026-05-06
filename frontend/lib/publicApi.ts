const getBaseUrl = () => {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return baseUrl.replace(/\/$/, '');
};

export async function fetchPublic<T = unknown>(url: string): Promise<T> {
  const baseUrl = getBaseUrl();
  const cleanUrl = url.replace(/^\//, '');
  const fullUrl = `${baseUrl}/${cleanUrl}`;
  
  const response = await fetch(fullUrl, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error('This project is not public');
    }
    if (response.status === 404) {
      throw new Error('Project not found');
    }
    throw new Error(`Failed to fetch: ${response.status} ${response.statusText}`);
  }
  
  return response.json();
}

export interface PublicProject {
  id: string;
  run_id?: string;
  title: string;
  description?: string;
  query?: string;
  total_references: number;
  relevant_references: number;
  status: string;
  created_at: string;
  created_by_name?: string;
}

export async function getPublicProject(projectId: string): Promise<{ project: PublicProject }> {
  return fetchPublic(`api/public/projects/${projectId}`);
}

export async function getPublicProjectSummary(projectId: string) {
  return fetchPublic(`api/public/projects/${projectId}/summary`);
}

export async function getPublicProjectDocuments(projectId: string) {
  return fetchPublic(`api/public/projects/${projectId}/documents`);
}

export async function getPublicProjectInterventions(projectId: string) {
  return fetchPublic(`api/public/projects/${projectId}/interventions`);
}

export async function getPublicProjectChartsData(projectId: string) {
  return fetchPublic(`api/public/projects/${projectId}/charts-data`);
}

export async function getPublicNavigator(projectId: string) {
  return fetchPublic(`api/public/projects/${projectId}/issue-intervention-navigator`);
}

export async function getPublicOutcomeContributions(
  projectId: string,
  outcomeThemeId: string
) {
  return fetchPublic(
    `api/public/projects/${projectId}/synthesis/outcome-themes/${outcomeThemeId}/contributions`
  );
}

export async function getPublicChunkContext(projectId: string, chunkId: string) {
  return fetchPublic(`api/public/projects/${projectId}/chunks/${chunkId}/context`);
}
