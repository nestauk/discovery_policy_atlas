import { useAuth } from "@clerk/nextjs";

export function useAPI() {
  const { getToken } = useAuth();
  
  const fetchWithAuth = async (url: string, options: RequestInit = {}) => {
    const token = await getToken();
    
    if (!token) {
      throw new Error("No authentication token available");
    }
    
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}${url}`, {
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