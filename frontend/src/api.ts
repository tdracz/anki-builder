const BASE = '/api'

export interface Word {
  id: number
  word: string
  language_code: string
  ipa: string | null
  audio_file: string | null
  image_file: string | null
  definitions: string[]
  etymology: string | null
  sentences: string[]
  synonyms: string[]
  antonyms: string[]
  translation: string | null
  translation_language: string | null
  pos: string | null
  source_url: string | null
  thesaurus_url: string | null
  deck_name: string | null
  anki_note_id: number | null
  scraped_at: string | null
  error_message: string | null
  status: 'pending' | 'done' | 'pending_sync' | 'pending_delete' | 'synced' | 'error' | 'not_found'
}

export interface AnkiStatus {
  connected: boolean
  version: number | null
  message: string
}

export interface LanguageInfo {
  code: string
  name: string
  deck: string
}

export interface DeckInfo {
  name: string
  is_app_deck: boolean
}

export interface ImportResult {
  total: number
  new: number
  duplicates: number
  words: string[]
  duplicate_words: string[]
}

export interface AnkiImportDuplicate {
  word: string
  language_code: string
  local_status: string
  local_anki_id: number | null
  anki_note_id: number
}

export interface AnkiImportPreview {
  total: number
  new: number
  duplicates: AnkiImportDuplicate[]
}

export interface AnkiImportResult {
  imported: number
  skipped: number
  overwritten: number
  errors: string[]
}

export interface SyncResult {
  synced: number
  failed: number
  errors: string[]
}

export interface WordUpdate {
  ipa?: string
  definitions?: string[]
  etymology?: string
  sentences?: string[]
  pos?: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  status: () => request<AnkiStatus>('/status'),
  languages: () => request<LanguageInfo[]>('/languages'),

  // Decks
  decks: (all = false) => request<DeckInfo[]>(`/decks${all ? '?all=true' : ''}`),
  lastUsedDeck: (lang = 'en') => request<{ deck_name: string | null }>(`/decks/last-used?lang=${lang}`),
  createDeck: (name: string) =>
    request<DeckInfo>('/decks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),

  // Words
  words: (lang?: string) =>
    request<Word[]>('/words' + (lang ? `?lang=${lang}` : '')),
  addWord: (lang: string, word: string, deck = '') =>
    request<Word>(`/words?lang=${lang}&word=${encodeURIComponent(word)}&deck=${encodeURIComponent(deck)}`, { method: 'POST' }),
  word: (lang: string, word: string) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}`),
  renameWord: (lang: string, word: string, newWord: string) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/rename?new_word=${encodeURIComponent(newWord)}`, { method: 'PUT' }),
  updateWord: (lang: string, word: string, body: WordUpdate, autoSync = false) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}?auto_sync=${autoSync}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteWord: (lang: string, word: string, autoSync = false) =>
    request<Word | undefined>(`/words/${lang}/${encodeURIComponent(word)}?auto_sync=${autoSync}`, { method: 'DELETE' }),
  rescrapeWord: (lang: string, word: string, autoSync = false) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/rescrape?auto_sync=${autoSync}`, { method: 'POST' }),
  setWordDeck: (lang: string, word: string, deckName: string, autoSync = false) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/deck?auto_sync=${autoSync}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: deckName }),
    }),

  // Image
  removeImage: (lang: string, word: string, autoSync = false) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/image?auto_sync=${autoSync}`, { method: 'DELETE' }),
  replaceImage: (lang: string, word: string, file: File, autoSync = false) => {
    const form = new FormData()
    form.append('file', file)
    return request<Word>(`/words/${lang}/${encodeURIComponent(word)}/image?auto_sync=${autoSync}`, {
      method: 'POST',
      body: form,
    })
  },

  // Import
  importFile: (file: File, lang: string, deck: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('lang', lang)
    form.append('deck', deck)
    return request<ImportResult>('/import', { method: 'POST', body: form })
  },
  importStream: (words: string[], lang: string, deck: string, autoSync = false, fetchImages = false, rescrape = false): EventSource => {
    const params = new URLSearchParams({ words: words.join(','), lang, deck, auto_sync: String(autoSync), fetch_images: String(fetchImages), rescrape: String(rescrape) })
    return new EventSource(`${BASE}/import/stream?${params}`)
  },

  // Bulk operations
  bulkDelete: (lang: string, words: string[], autoSync = false) =>
    request<{ deleted: number; queued: number }>('/words/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, words, auto_sync: autoSync }),
    }),
  undeleteWord: (lang: string, word: string) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/undelete`, { method: 'POST' }),
  bulkUndelete: (lang: string, words: string[]) =>
    request<{ restored: number }>('/words/bulk-undelete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, words }),
    }),
  bulkRescrape: (lang: string, words: string[]) =>
    request<{ rescraping: number }>('/words/bulk-rescrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, words }),
    }),
  bulkSync: (lang: string, words: string[], deck?: string) =>
    request<{ synced: number; failed: number; errors: string[] }>('/words/bulk-sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, words, deck }),
    }),
  bulkTranslate: (lang: string, words: string[]) =>
    request<{ translated: number; failed: number }>('/words/bulk-translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lang, words }),
    }),
  translateWord: (lang: string, word: string) =>
    request<Word>(`/words/${lang}/${encodeURIComponent(word)}/translate`, { method: 'POST' }),

  // Import from Anki
  ankiImportPreview: (deck: string) =>
    request<AnkiImportPreview>(`/import/anki/preview?deck=${encodeURIComponent(deck)}`),
  ankiImportExecute: (body: {
    deck_name: string
    duplicate_action: string
    skip_words: string[]
    overwrite_words: string[]
  }) =>
    request<AnkiImportResult>('/import/anki', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  cancelImport: () =>
    request<{ cancelled: boolean }>('/import/cancel', { method: 'POST' }),

  // Settings
  getSettings: () => request<Record<string, string>>('/settings'),
  getOpenAIModels: () => request<{ models: string[] }>('/settings/models'),
  updateSettings: (settings: Record<string, string>) =>
    request<Record<string, string>>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),

  // Translation
  translate: (lang: string) =>
    request<{ translated: number; failed: number; skipped: number; errors: string[] }>(
      `/translate?lang=${lang}`, { method: 'POST' }
    ),
  translateStream: (words: string[], lang: string): EventSource => {
    const params = new URLSearchParams({ words: words.join(','), lang })
    return new EventSource(`${BASE}/translate/stream?${params}`)
  },

  // Export
  exportWords: (lang: string) => {
    // Triggers a file download directly — no fetch needed
    const a = document.createElement('a')
    a.href = `${BASE}/export?lang=${lang}`
    a.download = `${lang}_words.txt`
    a.click()
  },

  // Sync
  sync: (lang?: string) =>
    request<SyncResult>('/sync' + (lang ? `?lang=${lang}` : ''), { method: 'POST' }),
  syncStream: (lang: string): EventSource =>
    new EventSource(`/api/sync/stream?lang=${lang}`),

  mediaUrl: (filename: string) => `${BASE}/media/${encodeURIComponent(filename)}`,
}
