// Utility to create password hashes for testing
import bcrypt from 'bcryptjs'

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 12)
}

// To generate a hash for testing:
// console.log(await hashPassword('password123'))