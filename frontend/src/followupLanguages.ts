export const followupLanguages = ['English', 'French', 'German', 'Spanish', 'Italian', 'Portuguese', 'Dutch', 'Polish', 'Arabic', 'Hebrew', 'Japanese', 'Korean', 'Mandarin Chinese']

export function emailLanguageCode(value: string | null | undefined): string {
  const language = (value ?? '').trim().toLowerCase()
  return ({ english: 'en', anglais: 'en', french: 'fr', français: 'fr' } as Record<string, string>)[language] ?? language
}
