import { existsSync, readFileSync } from 'fs'
import path from 'path'

function resolveDocumentPath(fileName: string): string {
  const workingDirectory = process.cwd()
  const candidatePaths = [
    path.join(workingDirectory, 'legal', fileName),
    path.join(workingDirectory, 'frontend', 'legal', fileName),
    path.join(workingDirectory, '..', 'frontend', 'legal', fileName),
  ]

  const resolvedPath = candidatePaths.find((candidatePath) => existsSync(candidatePath))
  if (!resolvedPath) {
    throw new Error(`Unable to locate legal document: ${fileName}`)
  }

  return resolvedPath
}

export function readLegalDocument(fileName: string): string {
  return readFileSync(resolveDocumentPath(fileName), 'utf-8')
}
