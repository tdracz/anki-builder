import { useEffect, useRef, useState } from 'react'
import { useStore } from './store/useStore'
import { AnkiStatus } from './components/AnkiStatus'
import { LanguageSelector } from './components/LanguageSelector'
import { DeckSelector } from './components/DeckSelector'
import { ImportPanel } from './components/ImportPanel'
import { WordList } from './components/WordList'
import { CardPreview } from './components/CardPreview'
import { SettingsPage } from './components/SettingsPage'

const MIN_PREVIEW_WIDTH = 380
const MAX_PREVIEW_WIDTH = 1200
const DEFAULT_PREVIEW_WIDTH = 900

export default function App() {
  const { loadLanguages, loadWords, checkAnkiStatus, selectedWord, error, clearError, importing } = useStore()
  const [importOpen, setImportOpen] = useState(false)
  const [page, setPage] = useState<'main' | 'settings'>('main')
  const [previewWidth, setPreviewWidth] = useState(DEFAULT_PREVIEW_WIDTH)
  const dragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(DEFAULT_PREVIEW_WIDTH)

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadLanguages(); loadWords(); checkAnkiStatus() }, [])

  // When importing is active the panel is always open; otherwise respect user toggle.
  const isImportOpen = importing || importOpen

  const onMouseDown = (e: React.MouseEvent) => {
    dragging.current = true
    startX.current = e.clientX
    startWidth.current = previewWidth
    e.preventDefault()
  }

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return
      const delta = startX.current - e.clientX
      const next = Math.min(MAX_PREVIEW_WIDTH, Math.max(MIN_PREVIEW_WIDTH, startWidth.current + delta))
      setPreviewWidth(next)
    }
    const onUp = () => { dragging.current = false }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
  }, [])

  if (page === 'settings') {
    return <SettingsPage onBack={() => setPage('main')} />
  }

  return (
    <div className="h-screen bg-gray-50 text-gray-900 flex flex-col select-none overflow-hidden">
      {/* Top bar */}
      <header className="flex items-center justify-between px-5 py-3 bg-white border-b border-gray-200 shadow-sm shrink-0 gap-4 flex-wrap">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight text-gray-800">Vocab Builder</h1>
          <LanguageSelector />
          <DeckSelector />
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setPage('settings')}
            title="Settings"
            className="text-base px-3 py-1.5 rounded border border-gray-300 text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
          >
            ⚙
          </button>
          <AnkiStatus />
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-5 py-2.5 text-base text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={clearError} className="text-red-400 hover:text-red-600 ml-4 text-lg">×</button>
        </div>
      )}

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left: collapsible import panel */}
        <aside className={`shrink-0 border-r border-gray-200 bg-white flex flex-col transition-all duration-200 ${isImportOpen ? 'w-80' : 'w-10'}`}>
          {/* Panel header / toggle */}
          <button
            onClick={() => setImportOpen(v => !v)}
            className="flex items-center gap-2 px-3 py-3.5 text-sm font-semibold uppercase tracking-widest text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors border-b border-gray-100 w-full text-left"
          >
            <span className={`transition-transform duration-200 text-base ${isImportOpen ? '' : 'rotate-180'}`}>‹</span>
            {isImportOpen && <span>Import</span>}
          </button>

          {isImportOpen && (
            <div className="p-5 overflow-y-auto flex-1">
              <ImportPanel />
            </div>
          )}
        </aside>

        {/* Center: word list */}
        <main className="flex-1 min-w-0 p-5 overflow-hidden flex flex-col bg-gray-50">
          <WordList />
        </main>

        {/* Drag handle */}
        <div
          onMouseDown={onMouseDown}
          className="w-1.5 shrink-0 bg-gray-200 hover:bg-blue-400 cursor-col-resize transition-colors active:bg-blue-500"
          title="Drag to resize"
        />

        {/* Right: card preview */}
        <aside
          style={{ width: previewWidth }}
          className="shrink-0 border-l border-gray-200 bg-white p-6 overflow-y-auto"
        >
          <h2 className="text-sm uppercase tracking-widest text-gray-400 font-semibold mb-4">Card Preview</h2>
          {selectedWord ? (
            <CardPreview word={selectedWord} />
          ) : (
            <p className="text-gray-400 text-base">Select a word to preview its card.</p>
          )}
        </aside>
      </div>
    </div>
  )
}
