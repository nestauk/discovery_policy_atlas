import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, } from '@testing-library/react';

// Track mock token and getToken behavior
let mockToken: string | null = 'mock-token-123';
let mockGetTokenError: Error | null = null;

// Mock the auth module
vi.mock('@/lib/auth', () => ({
  useAuthToken: () => ({
    getToken: async () => {
      if (mockGetTokenError) throw mockGetTokenError;
      return mockToken;
    },
  }),
  getTokenExternal: async () => {
    if (mockGetTokenError) throw mockGetTokenError;
    return mockToken;
  },
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Store original env
const originalEnv = process.env;

beforeEach(() => {
  mockToken = 'mock-token-123';
  mockGetTokenError = null;
  mockFetch.mockReset();
  
  process.env = {
    ...originalEnv,
    NEXT_PUBLIC_API_URL: 'http://localhost:8000',
    NODE_ENV: 'production', // Important: controls error throwing behavior
  };
  
  // Suppress console logs
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  process.env = originalEnv;
  vi.clearAllMocks();
});

describe('pingBackend', () => {
  it('returns true when backend is healthy', async () => {
    mockFetch.mockResolvedValueOnce({ ok: true });
    
    const { pingBackend } = await import('@/lib/api');
    const result = await pingBackend();
    
    expect(result).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/health',
      expect.objectContaining({ method: 'GET', cache: 'no-store' })
    );
  });

  it('returns false when backend returns non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false });
    
    const { pingBackend } = await import('@/lib/api');
    const result = await pingBackend();
    
    expect(result).toBe(false);
  });

  it('returns false when fetch throws error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    
    const { pingBackend } = await import('@/lib/api');
    const result = await pingBackend();
    
    expect(result).toBe(false);
  });
});

describe('fetchWithAuthExternal', () => {
  it('makes authenticated request with Bearer token', async () => {
    mockToken = 'my-access-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: 'test' }),
    });
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    const result = await fetchWithAuthExternal('api/test');
    
    expect(result).toEqual({ data: 'test' });
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/test',
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    );
    
    // Check headers
    const callHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(callHeaders.get('Authorization')).toBe('Bearer my-access-token');
    expect(callHeaders.get('Content-Type')).toBe('application/json');
  });

  it('throws error when no token available', async () => {
    mockToken = null;
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    
    await expect(fetchWithAuthExternal('api/test')).rejects.toThrow(
      'No authentication token available'
    );
  });

  it('handles streaming responses', async () => {
    mockToken = 'stream-token';
    const mockResponse = { ok: true, body: 'stream' };
    mockFetch.mockResolvedValueOnce(mockResponse);
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    const result = await fetchWithAuthExternal('api/stream', {}, true);
    
    // Should return raw response for streaming
    expect(result).toBe(mockResponse);
  });

  it('handles 401 errors with specific message', async () => {
    mockToken = 'expired-token';
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: 'Unauthorized',
      text: async () => 'Token expired',
    });
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    
    await expect(fetchWithAuthExternal('api/protected')).rejects.toThrow(
      'Authentication failed'
    );
  });

  it('handles non-401 errors', async () => {
    mockToken = 'valid-token';
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'Server crashed',
    });
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    
    await expect(fetchWithAuthExternal('api/broken')).rejects.toThrow(
      'API call failed: 500 Internal Server Error'
    );
  });

  it('does not set Content-Type for FormData', async () => {
    mockToken = 'form-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ uploaded: true }),
    });
    
    const formData = new FormData();
    formData.append('file', new Blob(['test']), 'test.txt');
    
    const { fetchWithAuthExternal } = await import('@/lib/api');
    await fetchWithAuthExternal('api/upload', { method: 'POST', body: formData });
    
    const callHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    // Content-Type should not be set for FormData (browser sets it with boundary)
    expect(callHeaders.get('Content-Type')).toBe(null);
  });

  it('cleans URL slashes correctly', async () => {
    mockToken = 'valid-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8000/';
    
    vi.resetModules();
    const { fetchWithAuthExternal } = await import('@/lib/api');
    await fetchWithAuthExternal('/api/test');
    
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/test',
      expect.any(Object)
    );
  });
});

describe('useAPI', () => {
  it('fetchWithAuth makes authenticated requests', async () => {
    mockToken = 'hook-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ result: 'success' }),
    });
    
    const { useAPI } = await import('@/lib/api');
    const { result } = renderHook(() => useAPI());
    
    const response = await result.current.fetchWithAuth('api/data');
    
    expect(response).toEqual({ result: 'success' });
  });

  it('getAnalysisProjects calls correct endpoint', async () => {
    mockToken = 'projects-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ projects: [], total: 0 }),
    });
    
    const { useAPI } = await import('@/lib/api');
    const { result } = renderHook(() => useAPI());
    
    const response = await result.current.getAnalysisProjects();
    
    expect(response).toEqual({ projects: [], total: 0 });
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/analysis-projects',
      expect.any(Object)
    );
  });

  it('createAnalysisProject sends POST request with body', async () => {
    mockToken = 'create-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ id: 'proj-123', title: 'New Project' }),
    });
    
    const { useAPI } = await import('@/lib/api');
    const { result } = renderHook(() => useAPI());
    
    await result.current.createAnalysisProject({
      title: 'New Project',
      description: 'Test project',
    });
    
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/analysis-projects',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          title: 'New Project',
          description: 'Test project',
        }),
      })
    );

    const callHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(callHeaders.get('Authorization')).toBe('Bearer create-token');
  });

  it('deleteAnalysisProject sends DELETE request', async () => {
    mockToken = 'delete-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({}),
    });
    
    const { useAPI } = await import('@/lib/api');
    const { result } = renderHook(() => useAPI());
    
    await result.current.deleteAnalysisProject('proj-456');
    
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/analysis-projects/proj-456',
      expect.objectContaining({ method: 'DELETE' })
    );

    const callHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(callHeaders.get('Authorization')).toBe('Bearer delete-token');
  });

  it('updateAnalysisProject sends PUT request with auth header', async () => {
    mockToken = 'update-token';
    mockFetch.mockResolvedValueOnce({
      ok: true,
      headers: new Headers(),
      json: async () => ({ id: 'proj-789', title: 'Updated' }),
    });

    const { useAPI } = await import('@/lib/api');
    const { result } = renderHook(() => useAPI());

    await result.current.updateAnalysisProject('proj-789', { title: 'Updated' });

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/analysis-projects/proj-789',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ title: 'Updated' }),
      })
    );

    const callHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(callHeaders.get('Authorization')).toBe('Bearer update-token');
  });
});
