import { useState } from 'react'
import { useStore } from '../store/useStore'

export function DeckSelector() {
  const {
    decks, selectedDeck, setDeck, createDeck,
    ankiStatus, showAllDecks, setShowAllDecks,
  } = useStore()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false)

  const connected = ankiStatus?.connected ?? false

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    await createDeck(name)
    setNewName('')
    setCreating(false)
    setBusy(false)
  }

  return (
    <div className="flex items-center gap-2">
      <label className="text-sm text-gray-500 shrink-0">Deck:</label>

      {!creating ? (
        <>
          <select
            value={selectedDeck}
            disabled={!connected}
            onChange={(e) => {
              if (e.target.value === '__new__') { setCreating(true); return }
              setDeck(e.target.value)
            }}
            className="text-base rounded border border-gray-300 bg-white text-gray-700 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400 max-w-[220px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {!connected && (
              <option value="">Not connected</option>
            )}
            {connected && decks.length === 0 && (
              <option value="" disabled>No app decks yet</option>
            )}
            {connected && decks.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}{showAllDecks && !d.is_app_deck ? ' ·' : ''}
              </option>
            ))}
            {connected && <option value="__new__">+ New deck…</option>}
          </select>

          {connected && (
            <button
              onClick={() => setShowAllDecks(!showAllDecks)}
              title={showAllDecks ? 'Showing all Anki decks — click to show only app decks' : 'Showing app decks only — click to show all Anki decks'}
              className={`text-sm px-2.5 py-1.5 rounded border transition-colors ${
                showAllDecks
                  ? 'border-blue-400 text-blue-600 bg-blue-50'
                  : 'border-gray-300 text-gray-500 hover:border-gray-400'
              }`}
            >
              {showAllDecks ? 'All' : 'Ours'}
            </button>
          )}
        </>
      ) : (
        <div className="flex items-center gap-1.5">
          <input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreating(false) }}
            placeholder="Deck name"
            className="text-base rounded border border-gray-300 px-3 py-1.5 w-40 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={handleCreate}
            disabled={busy || !newName.trim()}
            className="text-sm px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
          >
            {busy ? '…' : 'Create'}
          </button>
          <button
            onClick={() => setCreating(false)}
            className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-500 hover:border-gray-400"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  )
}
