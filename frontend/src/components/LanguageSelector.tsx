import { useStore } from '../store/useStore'

export function LanguageSelector() {
  const { languages, selectedLang, setLang } = useStore()

  if (languages.length <= 1) return null

  return (
    <select
      value={selectedLang}
      onChange={(e) => setLang(e.target.value)}
      className="text-base rounded border border-gray-300 bg-white text-gray-700 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
    >
      {languages.map((l) => (
        <option key={l.code} value={l.code}>
          {l.name}
        </option>
      ))}
    </select>
  )
}
