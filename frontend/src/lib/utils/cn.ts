import { clsx, type ClassValue } from 'clsx';

export type { ClassValue };

/**
 * Klassname-Utility — KEIN tailwind-merge.
 * Dieses Projekt nutzt kein Tailwind. clsx allein reicht für
 * conditional class composition.
 */
export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs);
}
