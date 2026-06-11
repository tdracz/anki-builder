import { useRef, useState } from 'react'
import type { Word } from '../api'
import { useStore } from '../store/useStore'
import { api } from '../api'

interface Props {
  word: Word
}

function DefinitionsList({ definitions }: { definitions: string[] }) {
  if (definitions.length === 0)
    return <p className="text-gray-400 text-base italic">No definitions scraped yet.</p>

  type Group = { pos: string | null; items: { text: string; subs: string[] }[] }
  const groups: Group[] = []
  let current: Group = { pos: null, items: [] }

  for (const entry of definitions) {
    if (entry.startsWith('__pos:') && entry.endsWith('__')) {
      if (current.items.length > 0) groups.push(current)
      current = { pos: entry.slice(6, -2), items: [] }
    } else if (entry.startsWith('__sub__')) {
      // Attach to the last main item, or create a virtual parent
      if (current.items.length === 0) {
        current.items.push({ text: '', subs: [] })
      }
      current.items[current.items.length - 1].subs.push(entry.slice(7))
    } else {
      current.items.push({ text: entry, subs: [] })
    }
  }
  if (current.items.length > 0) groups.push(current)

  return (
    <div className="space-y-4">
      {groups.map((group, gi) => (
        <div key={gi}>
          {group.pos && (
            <p className="text-sm text-blue-500 font-semibold uppercase tracking-wide mb-1.5 italic">
              {group.pos}
            </p>
          )}
          <ol className="list-decimal list-outside ml-5 space-y-1.5">
            {group.items.map((item, di) => (
              <li key={di} className="text-gray-700 text-base leading-relaxed">
                {item.text}
                {item.subs.length > 0 && (
                  <ol className="list-[lower-alpha] list-outside ml-5 mt-1 space-y-1">
                    {item.subs.map((sub, si) => (
                      <li key={si} className="text-gray-600 text-base leading-relaxed">{sub}</li>
                    ))}
                  </ol>
                )}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}

export function CardPreview({ word }: Props) {
  const { updateWord, deleteWord, rescrapeWord, removeImage, replaceImage, translateWord, renameWord } = useStore()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Partial<Word>>({})
  const [saving, setSaving] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [rescraping, setRescraping] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [newName, setNewName] = useState('')
  const imageInputRef = useRef<HTMLInputElement>(null)

  const current = { ...word, ...draft }

  const startEdit = () => {
    setDraft({
      ipa: word.ipa ?? '',
      etymology: word.etymology ?? '',
      definitions: [...(word.definitions ?? [])],
      sentences: [...(word.sentences ?? [])],
    })
    setEditing(true)
  }

  const save = async () => {
    setSaving(true)
    try {
      await updateWord(word.word, draft)
      setEditing(false)
      setDraft({})
    } finally {
      setSaving(false)
    }
  }

  const cancel = () => { setEditing(false); setDraft({}) }

  const handleDelete = async () => {
    if (!confirming) { setConfirming(true); return }
    await deleteWord(word.word)
    setConfirming(false)
  }

  const handleRescrape = async () => {
    setRescraping(true)
    try { await rescrapeWord(word.word) }
    finally { setRescraping(false) }
  }

  const handleTranslate = async () => {
    setTranslating(true)
    try { await translateWord(word.word) }
    finally { setTranslating(false) }
  }

  const handleReplaceImage = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) replaceImage(word.word, file)
    e.target.value = ''
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h2 className="text-4xl font-bold text-gray-900 break-words">
            {!renaming ? (
              <span>
                {word.word}
                <button
                  onClick={() => { setRenaming(true); setNewName(word.word) }}
                  title="Rename word"
                  className="ml-2 text-base text-gray-300 hover:text-blue-500 transition-colors align-middle"
                >✎</button>
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <input
                  autoFocus
                  value={newName}
                  onChange={e => setNewName(e.target.value)}
                  onKeyDown={async e => {
                    if (e.key === 'Enter' && newName.trim() && newName.trim() !== word.word) {
                      await renameWord(word.word, newName.trim()); setRenaming(false)
                    }
                    if (e.key === 'Escape') setRenaming(false)
                  }}
                  className="text-4xl font-bold text-gray-900 border-b-2 border-blue-400 outline-none bg-transparent w-full"
                />
                <button onClick={async () => { if (newName.trim() && newName.trim() !== word.word) { await renameWord(word.word, newName.trim()) } setRenaming(false) }}
                  className="text-sm px-2 py-1 rounded bg-blue-600 text-white hover:bg-blue-500">✓</button>
                <button onClick={() => setRenaming(false)}
                  className="text-sm px-2 py-1 rounded border border-gray-300 text-gray-500">×</button>
              </span>
            )}
          </h2>
          {!editing ? (
            current.ipa && <p className="text-gray-500 font-mono text-lg mt-1.5">{current.ipa}</p>
          ) : (
            <input
              value={(draft.ipa as string) ?? ''}
              onChange={(e) => setDraft((d) => ({ ...d, ipa: e.target.value }))}
              placeholder="IPA pronunciation"
              className="mt-1.5 w-full rounded border border-gray-300 text-gray-600 font-mono px-3 py-1.5 text-base focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
          )}
          {current.pos && (
            <span className="inline-block mt-1.5 text-sm text-blue-600 bg-blue-50 border border-blue-200 rounded px-2.5 py-0.5 uppercase tracking-wide font-medium">
              {current.pos}
            </span>
          )}
          {word.deck_name && (
            <span className="inline-block mt-1.5 ml-1.5 text-sm text-gray-400 bg-gray-100 rounded px-2.5 py-0.5">
              {word.deck_name}
            </span>
          )}
        </div>

        <div className="flex flex-col items-end gap-2 shrink-0">
          {word.audio_file && (
            <audio controls src={api.mediaUrl(word.audio_file)} className="h-9 w-44"
              onError={(e) => (e.currentTarget.style.display = 'none')} />
          )}
          <div className="flex gap-1.5 flex-wrap justify-end">
            {!editing ? (
              <button onClick={startEdit}
                className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors">
                Edit
              </button>
            ) : (
              <>
                <button onClick={save} disabled={saving}
                  className="text-sm px-3 py-1.5 rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
                  {saving ? '…' : 'Save'}
                </button>
                <button onClick={cancel}
                  className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-600">
                  Cancel
                </button>
              </>
            )}
            <button onClick={handleRescrape} disabled={rescraping}
              title="Re-scrape from dictionary"
              className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:border-orange-400 hover:text-orange-600 disabled:opacity-50 transition-colors">
              {rescraping ? '…' : '↺ Rescrape'}
            </button>
            <button onClick={handleTranslate} disabled={translating}
              title="Translate this word"
              className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:border-purple-400 hover:text-purple-600 disabled:opacity-50 transition-colors">
              {translating ? '…' : '🌐 Translate'}
            </button>
            <button onClick={handleDelete}
              className={`text-sm px-3 py-1.5 rounded border transition-colors ${
                confirming
                  ? 'border-red-500 bg-red-500 text-white hover:bg-red-600'
                  : 'border-gray-300 text-gray-600 hover:border-red-400 hover:text-red-600'
              }`}>
              {confirming ? 'Confirm delete' : 'Delete'}
            </button>
            {confirming && (
              <button onClick={() => setConfirming(false)}
                className="text-sm px-3 py-1.5 rounded border border-gray-300 text-gray-500">
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Image */}
      <div>
        {word.image_file ? (
          <div className="relative group">
            <img src={api.mediaUrl(word.image_file)} alt={word.word}
              className="rounded-lg max-h-56 object-cover w-full border border-gray-100" />
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity rounded-lg flex items-center justify-center gap-3">
              <button onClick={() => imageInputRef.current?.click()}
                className="text-sm px-4 py-1.5 rounded bg-white text-gray-800 hover:bg-gray-100 font-medium">
                Replace
              </button>
              <button onClick={() => removeImage(word.word)}
                className="text-sm px-4 py-1.5 rounded bg-red-500 text-white hover:bg-red-600 font-medium">
                Remove
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => imageInputRef.current?.click()}
            className="w-full py-4 rounded-lg border-2 border-dashed border-gray-200 text-gray-400 text-base hover:border-blue-300 hover:text-blue-500 transition-colors">
            + Add image
          </button>
        )}
        <input ref={imageInputRef} type="file" accept="image/*" className="hidden" onChange={handleReplaceImage} />
      </div>

      {/* Error message */}
      {word.error_message && (word.status === 'error' || word.status === 'not_found') && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          {word.error_message}
        </div>
      )}

      {/* Definitions */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm uppercase tracking-widest text-gray-400 font-semibold">Definitions</h3>
          {word.source_url && (
            <a href={word.source_url} target="_blank" rel="noopener noreferrer"
              className="text-sm text-blue-500 hover:text-blue-700 hover:underline">
              View in dictionary →
            </a>
          )}
        </div>
        {!editing ? (
          <DefinitionsList definitions={current.definitions ?? []} />
        ) : (
          <textarea
            value={(draft.definitions as string[])?.filter(d => !d.startsWith('__pos:')).join('\n') ?? ''}
            onChange={(e) => setDraft((d) => ({ ...d, definitions: e.target.value.split('\n') }))}
            rows={6}
            className="w-full rounded border border-gray-300 text-gray-700 text-base px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="One definition per line"
          />
        )}
      </section>

      {/* Synonyms & Antonyms */}
      {((word.synonyms ?? []).length > 0 || (word.antonyms ?? []).length > 0) && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm uppercase tracking-widest text-gray-400 font-semibold">Synonyms & Antonyms</h3>
            {word.thesaurus_url && (
              <a href={word.thesaurus_url} target="_blank" rel="noopener noreferrer"
                className="text-sm text-blue-500 hover:text-blue-700 hover:underline">
                View in thesaurus →
              </a>
            )}
          </div>
          {(word.synonyms ?? []).length > 0 && (
            <div className="mb-2">
              <span className="text-sm text-gray-500 font-medium mr-2">Syn:</span>
              <span className="flex flex-wrap gap-1.5 inline">
                {(word.synonyms ?? []).map((s, i) => (
                  <span key={i} className="text-sm bg-green-50 text-green-700 rounded px-2 py-0.5 border border-green-200">
                    {s}
                  </span>
                ))}
              </span>
            </div>
          )}
          {(word.antonyms ?? []).length > 0 && (
            <div>
              <span className="text-sm text-gray-500 font-medium mr-2">Ant:</span>
              <span className="flex flex-wrap gap-1.5 inline">
                {(word.antonyms ?? []).map((s, i) => (
                  <span key={i} className="text-sm bg-red-50 text-red-600 rounded px-2 py-0.5 border border-red-200">
                    {s}
                  </span>
                ))}
              </span>
            </div>
          )}
        </section>
      )}

      {/* Sentences */}
      <section>
        <h3 className="text-sm uppercase tracking-widest text-gray-400 font-semibold mb-3">Example Sentences</h3>
        {!editing ? (
          (current.sentences ?? []).length > 0
            ? <ul className="space-y-2.5">
                {(current.sentences ?? []).map((s, i) => (
                  <li key={i} className="text-gray-600 text-base italic border-l-2 border-blue-200 pl-4">{s}</li>
                ))}
              </ul>
            : <p className="text-gray-400 text-base italic">No example sentences available.</p>
        ) : (
          <textarea
            value={(draft.sentences as string[])?.join('\n') ?? ''}
            onChange={(e) => setDraft((d) => ({ ...d, sentences: e.target.value.split('\n') }))}
            rows={5}
            className="w-full rounded border border-gray-300 text-gray-600 text-base px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
            placeholder="One sentence per line"
          />
        )}
      </section>

      {/* Translation */}
      {word.translation && (
        <section className="bg-blue-50 border border-blue-100 rounded-lg p-4">
          <h3 className="text-sm uppercase tracking-widest text-blue-400 font-semibold mb-2">
            Translation{word.translation_language ? ` (${word.translation_language})` : ''}
          </h3>
          <div className="text-gray-800 text-base prose prose-sm" dangerouslySetInnerHTML={{ __html: word.translation }} />
        </section>
      )}

      {/* Etymology */}
      <section>
        <h3 className="text-sm uppercase tracking-widest text-gray-400 font-semibold mb-3">Word Origin</h3>
        {!editing ? (
          current.etymology
            ? <p className="text-gray-600 text-base italic border-l-2 border-gray-200 pl-4">{current.etymology}</p>
            : <p className="text-gray-400 text-base italic">No etymology available.</p>
        ) : (
          <textarea
            value={(draft.etymology as string) ?? ''}
            onChange={(e) => setDraft((d) => ({ ...d, etymology: e.target.value }))}
            rows={3}
            className="w-full rounded border border-gray-300 text-gray-600 text-base px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        )}
      </section>

      {/* Footer */}
      <div className="pt-4 border-t border-gray-100 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-400">
        <div className="flex gap-4">
          <span>{word.language_code.toUpperCase()}</span>
          {word.anki_note_id && <span>Anki #{word.anki_note_id}</span>}
          {word.scraped_at && <span>Scraped {new Date(word.scraped_at).toLocaleDateString()}</span>}
        </div>
      </div>
    </div>
  )
}
