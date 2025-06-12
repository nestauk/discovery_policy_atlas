import { useAuth } from "@clerk/nextjs";

export function useAPI() {
  const { getToken } = useAuth();
  
  const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const token = await getToken();
    
    if (!token) {
      throw new Error("No authentication token available");
    }
    
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    // Remove trailing slash from baseUrl and leading slash from url if present
    const cleanBaseUrl = baseUrl.replace(/\/$/, '');
    const cleanUrl = url.replace(/^\//, '');
    
    const response = await fetch(`${cleanBaseUrl}/${cleanUrl}`, {
      ...options,
      headers: {
        ...options.headers,
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });
    
    if (!response.ok) {
      throw new Error(`API call failed: ${response.statusText}`);
    }
    
    return response.json();
  };
  
  return { fetchWithAuth };
} 