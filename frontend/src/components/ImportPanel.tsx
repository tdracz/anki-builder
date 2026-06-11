import { useRef, useState, useEffect } from 'react'
import type { DragEvent } from 'react'
import { useStore } from '../store/useStore'
import type { AnkiImportDuplicate } from '../api'

const STATUS_ICON: Record<string, string> = {
  scraping:           '🔍',
  scraped:            '📖',
  audio_done:         '🔊',
  image_done:         '🖼️',
  synced:             '✅',
  pending_sync:       '⏳',
  not_found:          '🔎',
  error:              '❌',
  translating:        '🌐',
  translated:         '✅',
  translation_failed: '⚠️',
}

interface Props {
  onDone?: () => void
}

function DuplicateDialog({
  duplicates,
  onResolve,
  onCancel,
  busy,
}: {
  duplicates: AnkiImportDuplicate[]
  onResolve: (opts: { duplicateAction: string; skipWords: string[]; overwriteWords: string[] }) => void
  onCancel: () => void
  busy: boolean
}) {
  const [perWord, setPerWord] = useState<Record<string, 'skip' | 'overwrite'>>({})
  const [globalAction, setGlobalAction] = useState<'skip' | 'overwrite'>('skip')

  const setWord = (word: string, action: 'skip' | 'overwrite') =>
    setPerWord(p => ({ ...p, [word]: action }))

  const handleResolve = (action: 'skip-all' | 'overwrite-all' | 'apply-selections') => {
    if (action === 'skip-all') {
      onResolve({ duplicateAction: 'skip', skipWords: [], overwriteWords: [] })
    } else if (action === 'overwrite-all') {
      onResolve({ duplicateAction: 'overwrite', skipWords: [], overwriteWords: [] })
    } else {
      const skipWords = duplicates.filter(d => (perWord[d.word] ?? globalAction) === 'skip').map(d => d.word)
      const overwriteWords = duplicates.filter(d => (perWord[d.word] ?? globalAction) === 'overwrite').map(d => d.word)
      onResolve({ duplicateAction: globalAction, skipWords, overwriteWords })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-base font-medium text-gray-700">
          {duplicates.length} duplicate{duplicates.length !== 1 ? 's' : ''} found
        </p>
        <div className="flex items-center gap-1.5 text-sm text-gray-500">
          Default:
          <button
            onClick={() => setGlobalAction('skip')}
            className={`px-2.5 py-1 rounded border transition-colors ${globalAction === 'skip' ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-300 hover:border-gray-400'}`}
          >Skip</button>
          <button
            onClick={() => setGlobalAction('overwrite')}
            className={`px-2.5 py-1 rounded border transition-colors ${globalAction === 'overwrite' ? 'border-orange-400 text-orange-600 bg-orange-50' : 'border-gray-300 hover:border-gray-400'}`}
          >Overwrite</button>
        </div>
      </div>

      <div className="max-h-52 overflow-y-auto rounded border border-gray-200 bg-gray-50 divide-y divide-gray-100">
        {duplicates.map(d => {
          const action = perWord[d.word] ?? globalAction
          return (
            <div key={d.word} className="flex items-center justify-between px-3 py-2">
              <div>
                <span className="font-mono text-base text-gray-800">{d.word}</span>
                <span className="ml-2 text-sm text-gray-400">{d.local_status}</span>
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={() => setWord(d.word, 'skip')}
                  className={`text-sm px-2.5 py-1 rounded border transition-colors ${action === 'skip' ? 'border-blue-400 text-blue-600 bg-blue-50' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}
                >Skip</button>
                <button
                  onClick={() => setWord(d.word, 'overwrite')}
                  className={`text-sm px-2.5 py-1 rounded border transition-colors ${action === 'overwrite' ? 'border-orange-400 text-orange-600 bg-orange-50' : 'border-gray-200 text-gray-400 hover:border-gray-300'}`}
                >Overwrite</button>
              </div>
            </div>
          )
        })}
      </div>

      <div className="flex gap-2 flex-wrap">
        <button onClick={() => handleResolve('skip-all')} disabled={busy}
          className="text-sm px-3 py-2 rounded border border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600 disabled:opacity-50 transition-colors">
          Skip All
        </button>
        <button onClick={() => handleResolve('overwrite-all')} disabled={busy}
          className="text-sm px-3 py-2 rounded border border-orange-300 text-orange-600 hover:bg-orange-50 disabled:opacity-50 transition-colors">
          Overwrite All
        </button>
        <button onClick={() => handleResolve('apply-selections')} disabled={busy}
          className="text-sm px-3 py-2 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors">
          {busy ? 'Importing…' : 'Apply selections'}
        </button>
        <button onClick={onCancel} disabled={busy}
          className="text-sm px-3 py-2 rounded border border-gray-300 text-gray-500 hover:border-gray-400 disabled:opacity-50 ml-auto">
          Cancel
        </button>
      </div>
    </div>
  )
}

export function ImportPanel({ onDone }: Props) {
  const {
    importing, importLabel, importTotal, importProgress, importFile, clearImportProgress, cancelImport,
    ankiStatus, selectedDeck,
    fetchImages, setFetchImages,
    ankiImportPreview, ankiImporting, importFromAnki, executeAnkiImport, clearAnkiImportPreview,
  } = useStore()
  const inputRef = useRef<HTMLInputElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [pasteError, setPasteError] = useState<string | null>(null)

  const connected = ankiStatus?.connected ?? false

  // Auto-scroll progress list to bottom when new events arrive
  useEffect(() => {
    if (progressRef.current) {
      progressRef.current.scrollTop = progressRef.current.scrollHeight
    }
  }, [importProgress])

  const handleFile = async (file: File) => {
    if (!file.name.endsWith('.txt')) {
      setFileError('Please upload a plain .txt file (one word per line).')
      return
    }
    setFileError(null)
    await importFile(file)
    onDone?.()
  }

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handlePaste = async () => {
    setPasteError(null)
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        setPasteError('Clipboard is empty.')
        return
      }
      // Convert clipboard text to a File object so we reuse the same import flow
      const blob = new Blob([text], { type: 'text/plain' })
      const file = new File([blob], 'clipboard.txt', { type: 'text/plain' })
      await importFile(file)
      onDone?.()
    } catch {
      setPasteError('Could not read clipboard. Make sure you have text copied.')
    }
  }

  const progressByWord = importProgress.reduce<Record<string, string[]>>((acc, ev) => {
    if (!acc[ev.word]) acc[ev.word] = []
    acc[ev.word].push(ev.status)
    return acc
  }, {})

  const hasProgress = Object.keys(progressByWord).length > 0

  return (
    <div className="space-y-5">
      {/* ---- File import ---- */}
      <div className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-400">From file</p>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => !importing && inputRef.current?.click()}
          className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors
            ${importing ? 'border-gray-200 bg-gray-50 cursor-default' : dragging ? 'border-blue-400 bg-blue-50 cursor-pointer' : 'border-gray-300 hover:border-gray-400 bg-white cursor-pointer'}`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".txt"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f) }}
          />
          <p className="text-gray-600 text-base">
            {importing
              ? `${importLabel} ${Object.keys(progressByWord).length}${importTotal ? '/' + importTotal : ''}`
              : 'Drop a .txt file here or click to browse'}
          </p>
          <p className="text-gray-400 text-sm mt-1">One word per line</p>
        </div>

        {importing && (
          <button
            onClick={cancelImport}
            className="w-full text-sm py-2 rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
          >
            ✕ Stop processing
          </button>
        )}

        {/* Paste from clipboard */}
        {!importing && (
          <button
            onClick={handlePaste}
            className="w-full text-base py-2 rounded border border-gray-300 bg-white text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
          >
            📋 Paste from clipboard
          </button>
        )}
        {pasteError && <p className="text-red-600 text-sm">{pasteError}</p>}

        {/* Fetch images option */}
        <label className="flex items-center gap-2.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={fetchImages}
            onChange={e => setFetchImages(e.target.checked)}
            disabled={importing}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-400 disabled:opacity-50"
          />
          <span className="text-base text-gray-600">Fetch images</span>
          <span className="text-sm text-gray-400">(slower)</span>
        </label>

        {fileError && <p className="text-red-600 text-sm">{fileError}</p>}

        {hasProgress && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-sm text-gray-400">Last import</span>
              <button onClick={clearImportProgress} className="text-sm text-gray-400 hover:text-gray-600 transition-colors">
                Clear
              </button>
            </div>
            <div ref={progressRef} className="max-h-44 overflow-y-auto rounded border border-gray-200 bg-gray-50 p-2.5 space-y-1.5">
              {Object.entries(progressByWord).map(([word, statuses]) => (
                <div key={word} className="flex items-center gap-2">
                  <span className="text-gray-700 w-36 truncate font-mono text-sm">{word}</span>
                  <span className="flex gap-0.5 text-base">
                    {statuses.map((s, i) => <span key={i} title={s}>{STATUS_ICON[s] ?? s}</span>)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ---- Import from Anki ---- */}
      <div className="space-y-3 pt-4 border-t border-gray-100">
        <p className="text-sm font-semibold uppercase tracking-widest text-gray-400">From Anki deck</p>

        {!connected ? (
          <p className="text-sm text-gray-400 italic">Connect to Anki to import from a deck.</p>
        ) : ankiImportPreview && ankiImportPreview.duplicates.length > 0 ? (
          <DuplicateDialog
            duplicates={ankiImportPreview.duplicates}
            busy={ankiImporting}
            onResolve={(opts) => executeAnkiImport(opts)}
            onCancel={clearAnkiImportPreview}
          />
        ) : (
          <div className="space-y-2.5">
            <p className="text-sm text-gray-500">
              Import all VocabBuilder cards from <strong>{selectedDeck || 'selected deck'}</strong> into the local database.
            </p>
            <button
              onClick={() => importFromAnki(selectedDeck)}
              disabled={ankiImporting || !selectedDeck}
              className="w-full text-base py-2.5 rounded border border-gray-300 bg-white text-gray-700 hover:border-blue-400 hover:text-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {ankiImporting ? 'Scanning…' : '↓ Import from Anki'}
            </button>
            {ankiImporting && (
              <button
                onClick={cancelImport}
                className="w-full text-sm py-2 rounded border border-red-300 text-red-600 hover:bg-red-50 transition-colors"
              >
                ✕ Stop processing
              </button>
            )}
            {ankiImportPreview && ankiImportPreview.duplicates.length === 0 && (
              <p className="text-sm text-green-600">
                ✓ Imported {ankiImportPreview.new} word{ankiImportPreview.new !== 1 ? 's' : ''}, no duplicates.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
