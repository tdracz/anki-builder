import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import type { SortingState } from '@tanstack/react-table'
import { useState, useMemo } from 'react'
import type { Word } from '../api'
import { useStore } from '../store/useStore'
import { api } from '../api'

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  pending:        { label: 'Pending',       cls: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  done:           { label: 'Done',          cls: 'bg-blue-100 text-blue-700 border-blue-200' },
  pending_sync:   { label: 'Queued',        cls: 'bg-orange-100 text-orange-700 border-orange-200' },
  pending_delete: { label: 'Delete queued', cls: 'bg-red-100 text-red-600 border-red-200' },
  synced:         { label: 'Synced',        cls: 'bg-green-100 text-green-700 border-green-200' },
  error:          { label: 'Error',         cls: 'bg-red-100 text-red-700 border-red-200' },
  not_found:      { label: 'Not found',     cls: 'bg-gray-100 text-gray-500 border-gray-200' },
}

const col = createColumnHelper<Word>()

export function WordList() {
  const { words, selectedWord, selectWord, loadWords, bulkDelete, undeleteWord, bulkUndelete, bulkRescrape, bulkTranslate, bulkSync, addWord } = useStore()
  const { selectedLang } = useStore()
  const [sorting, setSorting] = useState<SortingState>([{ id: 'word', desc: false }])
  const [globalFilter, setGlobalFilter] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [addingWord, setAddingWord] = useState(false)
  const [newWord, setNewWord] = useState('')

  const handleRefresh = async () => {
    setRefreshing(true)
    await loadWords()
    setSelected(new Set())
    setRefreshing(false)
  }

  const columns = useMemo(() => [
    col.display({
      id: 'select',
      header: ({ table }) => {
        const allRows = table.getRowModel().rows
        const allSelected = allRows.length > 0 && allRows.every(r => selected.has(r.original.word))
        const someSelected = allRows.some(r => selected.has(r.original.word))
        return (
          <input
            type="checkbox"
            checked={allSelected}
            ref={el => { if (el) el.indeterminate = someSelected && !allSelected }}
            onChange={() => {
              if (allSelected) setSelected(new Set())
              else setSelected(new Set(allRows.map(r => r.original.word)))
            }}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-400"
            onClick={e => e.stopPropagation()}
          />
        )
      },
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={selected.has(row.original.word)}
          onChange={() => {
            setSelected(prev => {
              const next = new Set(prev)
              next.has(row.original.word) ? next.delete(row.original.word) : next.add(row.original.word)
              return next
            })
          }}
          onClick={e => e.stopPropagation()}
          className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-400"
        />
      ),
    }),
    col.accessor('word', {
      header: 'Word',
      cell: (info) => <span className="font-medium text-gray-900 text-base">{info.getValue()}</span>,
    }),
    col.accessor('pos', {
      header: 'POS',
      cell: (info) => <span className="text-gray-500 text-sm">{info.getValue() ?? '—'}</span>,
    }),
    col.accessor('ipa', {
      header: 'IPA',
      cell: (info) => <span className="text-gray-500 text-sm font-mono">{info.getValue() ?? '—'}</span>,
    }),
    col.accessor('status', {
      header: 'Status',
      cell: (info) => {
        const s = STATUS_BADGE[info.getValue()] ?? { label: info.getValue(), cls: 'bg-gray-100 text-gray-600 border-gray-200' }
        const errorMsg = info.row.original.error_message
        return (
          <span
            className={`text-sm px-2.5 py-0.5 rounded-full font-medium border ${s.cls}`}
            title={errorMsg && (info.getValue() === 'error' || info.getValue() === 'not_found') ? errorMsg : undefined}
          >
            {s.label}
          </span>
        )
      },
    }),
    col.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => {
        if (row.original.status !== 'pending_delete') return null
        return (
          <button
            onClick={async (e) => {
              e.stopPropagation()
              await undeleteWord(row.original.word)
            }}
            title="Undo delete"
            className="text-sm px-2.5 py-1 rounded border border-gray-300 text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors"
          >
            Undo
          </button>
        )
      },
    }),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [selected, undeleteWord])

  const table = useReactTable({
    data: words,
    columns,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const selectedList = Array.from(selected)
  const selectedPendingDelete = selectedList.filter(w => words.find(r => r.word === w)?.status === 'pending_delete')
  const selectedDeletable = selectedList.filter(w => words.find(r => r.word === w)?.status !== 'pending_delete')

  const handleBulkDelete = async () => {
    if (selectedDeletable.length === 0) return
    setBulkBusy(true)
    await bulkDelete(selectedDeletable)
    setSelected(new Set())
    setBulkBusy(false)
  }

  const handleBulkUndelete = async () => {
    if (selectedPendingDelete.length === 0) return
    setBulkBusy(true)
    await bulkUndelete(selectedPendingDelete)
    setSelected(new Set())
    setBulkBusy(false)
  }

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Search + refresh + add */}
      <div className="flex gap-2">
        <input
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="Filter words…"
          className="flex-1 rounded border border-gray-300 bg-white text-gray-800 px-4 py-2 text-base focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        {addingWord ? (
          <div className="flex gap-1.5">
            <input
              autoFocus
              value={newWord}
              onChange={e => setNewWord(e.target.value)}
              onKeyDown={async e => {
                if (e.key === 'Enter' && newWord.trim()) { await addWord(newWord.trim()); setNewWord(''); setAddingWord(false) }
                if (e.key === 'Escape') { setAddingWord(false); setNewWord('') }
              }}
              placeholder="New word…"
              className="rounded border border-gray-300 bg-white text-gray-800 px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-blue-400 w-40"
            />
            <button
              onClick={async () => { if (newWord.trim()) { await addWord(newWord.trim()); setNewWord(''); setAddingWord(false) } }}
              className="px-3 py-2 rounded bg-blue-600 text-white text-base hover:bg-blue-500 transition-colors"
            >+</button>
            <button
              onClick={() => { setAddingWord(false); setNewWord('') }}
              className="px-3 py-2 rounded border border-gray-300 text-gray-500 text-base hover:border-gray-400 transition-colors"
            >×</button>
          </div>
        ) : (
          <button
            onClick={() => setAddingWord(true)}
            title="Add a word manually"
            className="px-3 py-2 rounded border border-gray-300 bg-white text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors text-base"
          >+ Add</button>
        )}
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          title="Refresh word list"
          className="px-3 py-2 rounded border border-gray-300 bg-white text-gray-500 hover:border-blue-400 hover:text-blue-600 disabled:opacity-50 transition-colors text-base"
        >
          {refreshing ? '…' : '↻'}
        </button>
        <button
          onClick={() => api.exportWords(selectedLang)}
          title="Export word list as .txt"
          className="px-3 py-2 rounded border border-gray-300 bg-white text-gray-500 hover:border-blue-400 hover:text-blue-600 transition-colors text-base"
        >
          ↓ Export
        </button>
      </div>

      {/* Bulk action toolbar */}
      {selectedList.length > 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 bg-blue-50 border border-blue-200 rounded text-base">
          <span className="text-blue-700 font-medium">{selectedList.length} selected</span>
          <span className="text-blue-300">|</span>
          {selectedPendingDelete.length > 0 && (
            <button
              onClick={handleBulkUndelete}
              disabled={bulkBusy}
              className="text-sm px-3 py-1.5 rounded border border-blue-400 text-blue-600 hover:bg-blue-100 disabled:opacity-50 transition-colors"
            >
              {bulkBusy ? '…' : `Undo delete ${selectedPendingDelete.length}`}
            </button>
          )}
          {selectedDeletable.length > 0 && (
            <button
              onClick={async () => { setBulkBusy(true); await bulkRescrape(selectedDeletable); setSelected(new Set()); setBulkBusy(false) }}
              disabled={bulkBusy}
              className="text-sm px-3 py-1.5 rounded border border-orange-300 text-orange-600 hover:bg-orange-50 disabled:opacity-50 transition-colors"
            >
              {bulkBusy ? '…' : `Rescrape ${selectedDeletable.length}`}
            </button>
          )}
          {selectedDeletable.length > 0 && (
            <button
              onClick={async () => { setBulkBusy(true); await bulkTranslate(selectedDeletable); setSelected(new Set()); setBulkBusy(false) }}
              disabled={bulkBusy}
              className="text-sm px-3 py-1.5 rounded border border-purple-300 text-purple-600 hover:bg-purple-50 disabled:opacity-50 transition-colors"
            >
              {bulkBusy ? '…' : `Translate ${selectedDeletable.length}`}
            </button>
          )}
          {selectedDeletable.length > 0 && (
            <button
              onClick={async () => { setBulkBusy(true); await bulkSync(selectedDeletable); setSelected(new Set()); setBulkBusy(false) }}
              disabled={bulkBusy}
              className="text-sm px-3 py-1.5 rounded border border-green-300 text-green-600 hover:bg-green-50 disabled:opacity-50 transition-colors"
            >
              {bulkBusy ? '…' : `Sync ${selectedDeletable.length}`}
            </button>
          )}
          {selectedDeletable.length > 0 && (
            <button
              onClick={handleBulkDelete}
              disabled={bulkBusy}
              className="text-sm px-3 py-1.5 rounded bg-red-500 hover:bg-red-600 text-white disabled:opacity-50 transition-colors"
            >
              {bulkBusy ? '…' : `Delete ${selectedDeletable.length}`}
            </button>
          )}
          <button
            onClick={() => setSelected(new Set())}
            className="ml-auto text-sm text-blue-400 hover:text-blue-600"
          >
            Clear selection
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-y-auto flex-1 rounded border border-gray-200 bg-white">
        <table className="w-full text-base">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    onClick={header.id !== 'select' && header.id !== 'actions' ? header.column.getToggleSortingHandler() : undefined}
                    className={`text-left px-4 py-3 text-gray-500 font-semibold text-sm uppercase tracking-wide select-none
                      ${header.id !== 'select' && header.id !== 'actions' ? 'cursor-pointer hover:text-gray-800' : ''}`}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' ? ' ↑' : header.column.getIsSorted() === 'desc' ? ' ↓' : ''}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center text-gray-400 py-12 text-base">
                  No words yet. Import a .txt file to get started.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => selectWord(row.original)}
                  className={`border-b border-gray-100 cursor-pointer transition-colors
                    ${selected.has(row.original.word) ? 'bg-blue-50' :
                      selectedWord?.word === row.original.word ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="text-sm text-gray-400">
        {table.getRowModel().rows.length} of {words.length} word{words.length !== 1 ? 's' : ''}
        {selectedList.length > 0 && ` · ${selectedList.length} selected`}
      </p>
    </div>
  )
}
