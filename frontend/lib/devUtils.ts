/**
 * Development utilities for cache management and debugging
 */

/**
 * Clear all Zustand stores and refresh the page
 * Useful when developing or when database has been reset
 */
export const clearAllCaches = () => {
  try {
    // Clear Zustand stores
    localStorage.removeItem('chatbot-storage')
    localStorage.removeItem('project-storage')
    
    // Clear any other localStorage items that might be related to the app
    const keysToRemove = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key && (key.includes('chatbot') || key.includes('project') || key.includes('search'))) {
        keysToRemove.push(key)
      }
    }
    
    keysToRemove.forEach(key => localStorage.removeItem(key))
    
    // Clear session storage as well
    sessionStorage.clear()
    
    console.log('All caches cleared successfully')
    
    // Reload the page to start fresh
    window.location.reload()
  } catch (error) {
    console.error('Error clearing caches:', error)
  }
}

/**
 * Clear only search-related caches without page reload
 */
export const clearSearchCaches = () => {
  try {
    // Get current chatbot storage
    const chatbotStorage = localStorage.getItem('chatbot-storage')
    if (chatbotStorage) {
      const parsed = JSON.parse(chatbotStorage)
      // Clear search results but keep other data
      parsed.state.searchResults = null
      parsed.state.searchCompleted = false
      parsed.state.searchInProgress = false
      localStorage.setItem('chatbot-storage', JSON.stringify(parsed))
    }
    
    console.log('Search caches cleared')
  } catch (error) {
    console.error('Error clearing search caches:', error)
  }
}

/**
 * Debug function to inspect current cache state
 */
export const inspectCaches = () => {
  console.group('Cache Inspection')
  
  try {
    // Chatbot storage
    const chatbotStorage = localStorage.getItem('chatbot-storage')
    if (chatbotStorage) {
      console.log('Chatbot Storage:', JSON.parse(chatbotStorage))
    }
    
    // Project storage
    const projectStorage = localStorage.getItem('project-storage')
    if (projectStorage) {
      console.log('Project Storage:', JSON.parse(projectStorage))
    }
    
    // All localStorage keys
    const allKeys = []
    for (let i = 0; i < localStorage.length; i++) {
      allKeys.push(localStorage.key(i))
    }
    console.log('All localStorage keys:', allKeys)
    
  } catch (error) {
    console.error('Error inspecting caches:', error)
  }
  
  console.groupEnd()
}

// Make functions available globally in development
declare global {
  interface Window {
    clearAllCaches?: () => void
    clearSearchCaches?: () => void
    inspectCaches?: () => void
  }
}

if (typeof window !== 'undefined' && process.env.NODE_ENV === 'development') {
  window.clearAllCaches = clearAllCaches
  window.clearSearchCaches = clearSearchCaches
  window.inspectCaches = inspectCaches
}