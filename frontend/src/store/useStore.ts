import { create } from 'zustand'
import { api } from '../api'
import type { Word, AnkiStatus, LanguageInfo, SyncResult, DeckInfo } from '../api'

interface ProgressEvent {
  word: string
  status: string
}

interface AppState {
  words: Word[]
  languages: LanguageInfo[]
  decks: DeckInfo[]
  ankiStatus: AnkiStatus | null
  selectedLang: string
  selectedDeck: string
  selectedWord: Word | null
  autoSync: boolean
  fetchImages: boolean
  showAllDecks: boolean
  importing: boolean
  importLabel: string
  importTotal: number   // total words in current batch
  importProgress: ProgressEvent[]
  ankiImportPreview: import('../api').AnkiImportPreview | null
  ankiImportDeck: string
  ankiImporting: boolean
  syncing: boolean
  lastSyncResult: SyncResult | null
  error: string | null

  loadLanguages: () => Promise<void>
  loadWords: (lang?: string) => Promise<void>
  loadDecks: () => Promise<void>
  checkAnkiStatus: () => Promise<void>
  selectWord: (word: Word | null) => void
  addWord: (word: string) => Promise<void>
  renameWord: (oldWord: string, newWord: string) => Promise<void>
  setLang: (lang: string) => void
  setDeck: (deck: string) => void
  setAutoSync: (enabled: boolean) => void
  setFetchImages: (enabled: boolean) => void
  setShowAllDecks: (show: boolean) => void
  createDeck: (name: string) => Promise<void>
  importFile: (file: File) => Promise<void>
  cancelImport: () => Promise<void>
  importFromAnki: (deckName: string) => Promise<void>
  executeAnkiImport: (opts: { duplicateAction: string; skipWords: string[]; overwriteWords: string[] }) => Promise<void>
  clearAnkiImportPreview: () => void
  updateWord: (word: string, update: Partial<Word>) => Promise<void>
  deleteWord: (word: string) => Promise<void>
  bulkDelete: (words: string[]) => Promise<void>
  undeleteWord: (word: string) => Promise<void>
  bulkUndelete: (words: string[]) => Promise<void>
  bulkSync: (words: string[]) => Promise<void>
  bulkRescrape: (words: string[]) => Promise<void>
  bulkTranslate: (words: string[]) => Promise<void>
  translateWord: (word: string) => Promise<void>
  rescrapeWord: (word: string) => Promise<void>
  removeImage: (word: string) => Promise<void>
  replaceImage: (word: string, file: File) => Promise<void>
  syncToAnki: () => Promise<void>
  clearError: () => void
  clearImportProgress: () => void
  _refreshWord: (word: string) => Promise<void>
}

// Active EventSource held outside Zustand (not serializable state)
let _activeEventSource: EventSource | null = null

// Statuses that indicate a word finished processing and should be refreshed in the list
const _COMPLETED_STATUSES = new Set(['scraped', 'pending_sync', 'synced', 'error', 'not_found', 'translated', 'translation_failed', 'sync_failed'])

export const useStore = create<AppState>((set, get) => ({  words: [],
  languages: [],
  decks: [],
  ankiStatus: null,
  selectedLang: 'en',
  selectedDeck: '',
  selectedWord: null,
  autoSync: localStorage.getItem('autoSync') === 'true',
  fetchImages: localStorage.getItem('fetchImages') === 'true',
  showAllDecks: false,
  importing: false,
  importLabel: 'Importing…',
  importTotal: 0,
  importProgress: [],
  ankiImportPreview: null,
  ankiImportDeck: '',
  ankiImporting: false,
  syncing: false,
  lastSyncResult: null,
  error: null,

  clearError: () => set({ error: null }),
  clearImportProgress: () => set({ importProgress: [] }),

  // Helper: refresh a single word in the list after it finishes processing
  _refreshWord: async (word: string) => {
    const lang = get().selectedLang
    try {
      const updated = await api.word(lang, word)
      set((s) => {
        const exists = s.words.some(w => w.word === word)
        const words = exists
          ? s.words.map(w => w.word === word ? updated : w)
          : [...s.words, updated].sort((a, b) => a.word.localeCompare(b.word))
        return {
          words,
          selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
        }
      })
    } catch { /* word may have been deleted — ignore */ }
  },

  loadLanguages: async () => {
    try {
      const languages = await api.languages()
      set({ languages })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  loadWords: async (lang?: string) => {
    const l = lang ?? get().selectedLang
    try {
      const words = await api.words(l)
      set({ words })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  loadDecks: async () => {
    const { showAllDecks, selectedLang } = get()
    try {
      const decks = await api.decks(showAllDecks)
      set({ decks })
      // Pre-select: use last used deck from DB, then first in list
      if (!get().selectedDeck) {
        try {
          const { deck_name } = await api.lastUsedDeck(selectedLang)
          const match = deck_name && decks.find(d => d.name === deck_name)
          set({ selectedDeck: match ? deck_name! : (decks[0]?.name ?? '') })
        } catch {
          set({ selectedDeck: decks[0]?.name ?? '' })
        }
      }
    } catch {
      // Anki may not be running — silently ignore
    }
  },

  checkAnkiStatus: async () => {
    try {
      const ankiStatus = await api.status()
      set({ ankiStatus })
      if (ankiStatus.connected) get().loadDecks()
    } catch (e) {
      set({ ankiStatus: { connected: false, version: null, message: String(e) } })
    }
  },

  selectWord: (word) => set({ selectedWord: word }),

  addWord: async (word: string) => {
    const { selectedLang: lang, selectedDeck: deck } = get()
    try {
      const created = await api.addWord(lang, word, deck)
      set((s) => ({ words: [...s.words, created].sort((a, b) => a.word.localeCompare(b.word)) }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  renameWord: async (oldWord: string, newWord: string) => {
    const lang = get().selectedLang
    try {
      const updated = await api.renameWord(lang, oldWord, newWord)
      set((s) => ({
        words: s.words.map(w => w.word === oldWord ? updated : w).sort((a, b) => a.word.localeCompare(b.word)),
        selectedWord: s.selectedWord?.word === oldWord ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  setLang: (lang) => {
    set({ selectedLang: lang, selectedWord: null })
    get().loadWords(lang)
  },

  setDeck: (deck) => set({ selectedDeck: deck }),

  setAutoSync: (enabled: boolean) => {
    localStorage.setItem('autoSync', String(enabled))
    set({ autoSync: enabled })
  },

  setFetchImages: (enabled: boolean) => {
    localStorage.setItem('fetchImages', String(enabled))
    set({ fetchImages: enabled })
  },

  setShowAllDecks: (show: boolean) => {
    set({ showAllDecks: show })
    get().loadDecks()
  },

  createDeck: async (name: string) => {
    try {
      await api.createDeck(name)
      await get().loadDecks()
      set({ selectedDeck: name })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  importFile: async (file: File) => {
    const { selectedLang: lang, selectedDeck: deck, autoSync, fetchImages } = get()
    set({ importing: true, importLabel: 'Importing…', importTotal: 0, importProgress: [], error: null })
    try {
      const result = await api.importFile(file, lang, deck)
      if (result.new > 0) {
        set({ importTotal: result.new })
        await new Promise<void>((resolve, reject) => {
          const es = api.importStream(result.words, lang, deck, autoSync, fetchImages)
          _activeEventSource = es
          es.onmessage = (e) => {
            const data = JSON.parse(e.data) as { word?: string; status?: string; message?: string }
            if (data.status === 'done' || data.status === 'cancelled') {
              es.close(); _activeEventSource = null; resolve(); return
            }
            if (data.status === 'error' && !data.word) {
              es.close(); _activeEventSource = null; reject(new Error(data.message ?? 'Import error')); return
            }
            set((s) => ({ importProgress: [...s.importProgress, data as ProgressEvent] }))
            if (data.word && data.status && _COMPLETED_STATUSES.has(data.status)) {
              get()._refreshWord(data.word)
            }
          }
          es.onerror = () => { es.close(); _activeEventSource = null; reject(new Error('Connection to import stream lost')) }
        })
      }
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ importing: false })
      await get().loadWords()
    }
  },

  cancelImport: async () => {
    // Close the SSE connection immediately so no more events arrive
    if (_activeEventSource) {
      _activeEventSource.close()
      _activeEventSource = null
    }
    // Tell the backend to stop the scrape loop
    try { await api.cancelImport() } catch { /* best effort */ }
    set({ importing: false, ankiImporting: false })
    await get().loadWords()
  },

  importFromAnki: async (deckName: string) => {
    set({ ankiImporting: true, ankiImportDeck: deckName, error: null })
    try {
      const preview = await api.ankiImportPreview(deckName)
      set({ ankiImportPreview: preview })
      // If no duplicates, execute immediately with default skip action
      if (preview.duplicates.length === 0) {
        await get().executeAnkiImport({ duplicateAction: 'skip', skipWords: [], overwriteWords: [] })
      }
      // Otherwise the UI shows the duplicate dialog
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ ankiImporting: false })
    }
  },

  executeAnkiImport: async ({ duplicateAction, skipWords, overwriteWords }) => {
    const deck = get().ankiImportDeck
    set({ ankiImporting: true, error: null })
    try {
      await api.ankiImportExecute({
        deck_name: deck,
        duplicate_action: duplicateAction,
        skip_words: skipWords,
        overwrite_words: overwriteWords,
      })
      set({ ankiImportPreview: null, ankiImportDeck: '' })
      await get().loadWords()
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ ankiImporting: false })
    }
  },

  clearAnkiImportPreview: () => set({ ankiImportPreview: null, ankiImportDeck: '' }),

  updateWord: async (word: string, update: Partial<Word>) => {    const { selectedLang: lang, autoSync } = get()
    try {
      const updated = await api.updateWord(lang, word, {
        ipa: update.ipa ?? undefined,
        definitions: update.definitions ?? undefined,
        etymology: update.etymology ?? undefined,
        sentences: update.sentences ?? undefined,
        pos: update.pos ?? undefined,
      }, autoSync)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  deleteWord: async (word: string) => {
    const { selectedLang: lang, autoSync } = get()
    try {
      const result = await api.deleteWord(lang, word, autoSync)
      if (autoSync || !result) {
        set((s) => ({
          words: s.words.filter((w) => w.word !== word),
          selectedWord: s.selectedWord?.word === word ? null : s.selectedWord,
        }))
      } else {
        set((s) => ({
          words: s.words.map((w) => (w.word === word ? result : w)),
          selectedWord: s.selectedWord?.word === word ? result : s.selectedWord,
        }))
      }
    } catch (e) {
      set({ error: String(e) })
    }
  },

  bulkDelete: async (words: string[]) => {
    const { selectedLang: lang, autoSync } = get()
    try {
      await api.bulkDelete(lang, words, autoSync)
      if (autoSync) {
        set((s) => ({
          words: s.words.filter((w) => !words.includes(w.word)),
          selectedWord: s.selectedWord && words.includes(s.selectedWord.word) ? null : s.selectedWord,
        }))
      } else {
        // Refresh to get updated pending_delete statuses
        await get().loadWords()
      }
    } catch (e) {
      set({ error: String(e) })
    }
  },

  undeleteWord: async (word: string) => {
    const lang = get().selectedLang
    try {
      const updated = await api.undeleteWord(lang, word)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  bulkUndelete: async (words: string[]) => {
    const lang = get().selectedLang
    try {
      await api.bulkUndelete(lang, words)
      await get().loadWords()
    } catch (e) {
      set({ error: String(e) })
    }
  },

  bulkSync: async (words: string[]) => {
    const { selectedLang: lang, selectedDeck: deck } = get()
    try {
      const result = await api.bulkSync(lang, words, deck)
      set({ lastSyncResult: result })
      await get().loadWords()
    } catch (e) {
      set({ error: String(e) })
    }
  },

  bulkRescrape: async (words: string[]) => {
    const { selectedLang: lang, selectedDeck: deck, autoSync, fetchImages } = get()
    set({ importing: true, importLabel: 'Rescraping…', importTotal: words.length, importProgress: [], error: null })
    try {
      await new Promise<void>((resolve, reject) => {
        const es = api.importStream(words, lang, deck, autoSync, fetchImages, true)
        _activeEventSource = es
        es.onmessage = (e) => {
          const data = JSON.parse(e.data) as { word?: string; status?: string; message?: string }
          if (data.status === 'done' || data.status === 'cancelled') {
            es.close(); _activeEventSource = null; resolve(); return
          }
          if (data.status === 'error' && !data.word) {
            es.close(); _activeEventSource = null; reject(new Error(data.message ?? 'Rescrape error')); return
          }
          set((s) => ({ importProgress: [...s.importProgress, data as { word: string; status: string }] }))
          if (data.word && data.status && _COMPLETED_STATUSES.has(data.status)) {
            get()._refreshWord(data.word)
          }
        }
        es.onerror = () => { es.close(); _activeEventSource = null; reject(new Error('Connection lost during rescrape')) }
      })
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ importing: false })
      await get().loadWords()
    }
  },

  bulkTranslate: async (words: string[]) => {
    const lang = get().selectedLang
    set({ importing: true, importLabel: 'Translating…', importTotal: words.length, importProgress: [], error: null })
    try {
      await new Promise<void>((resolve, reject) => {
        const es = api.translateStream(words, lang)
        _activeEventSource = es
        es.onmessage = (e) => {
          const data = JSON.parse(e.data) as { word?: string; status?: string; message?: string }
          if (data.status === 'done' || data.status === 'cancelled') {
            es.close(); _activeEventSource = null; resolve(); return
          }
          if (data.status === 'error' && !data.word) {
            es.close(); _activeEventSource = null; reject(new Error(data.message ?? 'Translation error')); return
          }
          set((s) => ({ importProgress: [...s.importProgress, data as { word: string; status: string }] }))
          if (data.word && data.status && _COMPLETED_STATUSES.has(data.status)) {
            get()._refreshWord(data.word)
          }
        }
        es.onerror = () => { es.close(); _activeEventSource = null; reject(new Error('Connection lost during translation')) }
      })
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ importing: false })
      await get().loadWords()
    }
  },

  translateWord: async (word: string) => {
    const lang = get().selectedLang
    try {
      const updated = await api.translateWord(lang, word)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  rescrapeWord: async (word: string) => {
    const { selectedLang: lang, autoSync } = get()
    try {
      const updated = await api.rescrapeWord(lang, word, autoSync)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  removeImage: async (word: string) => {
    const { selectedLang: lang, autoSync } = get()
    try {
      const updated = await api.removeImage(lang, word, autoSync)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  replaceImage: async (word: string, file: File) => {
    const { selectedLang: lang, autoSync } = get()
    try {
      const updated = await api.replaceImage(lang, word, file, autoSync)
      set((s) => ({
        words: s.words.map((w) => (w.word === word ? updated : w)),
        selectedWord: s.selectedWord?.word === word ? updated : s.selectedWord,
      }))
    } catch (e) {
      set({ error: String(e) })
    }
  },

  syncToAnki: async () => {
    const lang = get().selectedLang
    set({ syncing: true, error: null })
    try {
      await new Promise<void>((resolve, reject) => {
        const es = api.syncStream(lang)
        _activeEventSource = es
        let synced = 0
        let failed = 0

        es.onmessage = (e) => {
          const data = JSON.parse(e.data) as { word?: string; status?: string; message?: string }

          if (data.status === 'done' || data.status === 'cancelled' || data.status === 'nothing_to_sync') {
            es.close(); _activeEventSource = null
            set({ lastSyncResult: { synced, failed, errors: [] } })
            resolve(); return
          }
          if (data.status === 'error' && !data.word) {
            es.close(); _activeEventSource = null
            reject(new Error(data.message ?? 'Sync error')); return
          }

          // Real-time word list updates
          if (data.word) {
            if (data.status === 'synced') synced++
            if (data.status === 'sync_failed') failed++
            if (data.status === 'deleted') {
              synced++
              set((s) => ({
                words: s.words.filter(w => w.word !== data.word),
                selectedWord: s.selectedWord?.word === data.word ? null : s.selectedWord,
              }))
            } else if (data.status && _COMPLETED_STATUSES.has(data.status)) {
              get()._refreshWord(data.word)
            }
          }
        }
        es.onerror = () => { es.close(); _activeEventSource = null; reject(new Error('Connection lost during sync')) }
      })
    } catch (e) {
      set({ error: String(e) })
    } finally {
      set({ syncing: false })
      await get().loadDecks()
    }
  },
}))
