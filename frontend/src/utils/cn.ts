import { clsx, type ClassValue } from 'clsx'

/** Thin wrapper around clsx — the only class-name-joining helper used across the app. */
export function cn(...inputs: ClassValue[]): string {
  return clsx(...inputs)
}
