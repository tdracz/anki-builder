import { useEffect, useState } from 'react'
import { api } from '../api'

const LANGUAGES = [
  'None', 'Arabic', 'Chinese', 'Czech', 'Danish', 'Dutch', 'Finnish', 'French',
  'German', 'Greek', 'Hebrew', 'Hindi', 'Hungarian', 'Italian', 'Japanese',
  'Korean', 'Norwegian', 'Polish', 'Portuguese', 'Romanian', 'Russian',
  'Slovak', 'Spanish', 'Swedish', 'Thai', 'Turkish', 'Ukrainian', 'Vietnamese',
]

export function SettingsPage({ onBack }: { onBack: () => void }) {
  const [settings, setSettings] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [translating, setTranslating] = useState(false)
  const [translateResult, setTranslateResult] = useState<string | null>(null)
  const [models, setModels] = useState<string[]>([])
  const [fetchingModels, setFetchingModels] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)

  useEffect(() => {
    api.getSettings().then(setSettings)
  }, [])

  const update = (key: string, value: string) => {
    setSettings(s => ({ ...s, [key]: value }))
    setSaved(false)
  }

  const fetchModels = async () => {
    setFetchingModels(true)
    setModelsError(null)
    try {
      const result = await api.getOpenAIModels()
      setModels(result.models)
    } catch (e) {
      setModelsError(String(e))
    } finally {
      setFetchingModels(false)
    }
  }

  const save = async () => {
    setSaving(true)
    await api.updateSettings(settings)
    setSaving(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const handleTranslate = async () => {
    setTranslating(true)
    setTranslateResult(null)
    try {
      const result = await api.translate('en')
      setTranslateResult(
        `Translated: ${result.translated}, Failed: ${result.failed}` +
        (result.errors.length > 0 ? ` (${result.errors.join(', ')})` : '')
      )
    } catch (e) {
      setTranslateResult(`Error: ${e}`)
    } finally {
      setTranslating(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      {/* Header */}
      <header className="flex items-center gap-4 px-6 py-4 bg-white border-b border-gray-200 shadow-sm">
        <button
          onClick={onBack}
          className="text-base px-3 py-1.5 rounded border border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
        >
          ← Back
        </button>
        <h1 className="text-xl font-semibold text-gray-800">Settings</h1>
      </header>

      <div className="max-w-2xl mx-auto p-8 space-y-10">
        {/* ---- Translation section ---- */}
        <section className="space-y-5">
          <h2 className="text-lg font-semibold text-gray-800 border-b border-gray-200 pb-2">Translation</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-base font-medium text-gray-700 mb-1.5">Target Language</label>
              <select
                value={settings.translation_target_language || 'None'}
                onChange={e => update('translation_target_language', e.target.value)}
                className="w-full text-base rounded border border-gray-300 bg-white px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                {LANGUAGES.map(l => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
              <p className="text-sm text-gray-400 mt-1">
                Words will be automatically translated to this language after import.
                Set to "None" to disable.
              </p>
            </div>

            <div>
              <label className="block text-base font-medium text-gray-700 mb-1.5">OpenAI API Key</label>
              <input
                type="password"
                value={settings.openai_api_key || ''}
                onChange={e => update('openai_api_key', e.target.value)}
                placeholder="sk-..."
                className="w-full text-base rounded border border-gray-300 px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <p className="text-sm text-gray-400 mt-1">
                Required for translation. Get one at{' '}
                <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                  platform.openai.com
                </a>
              </p>
            </div>

            <div>
              <label className="block text-base font-medium text-gray-700 mb-1.5">AI Model</label>
              <div className="flex gap-2">
                {models.length > 0 ? (
                  <select
                    value={settings.openai_model || 'gpt-4o-mini'}
                    onChange={e => update('openai_model', e.target.value)}
                    className="flex-1 text-base rounded border border-gray-300 bg-white px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  >
                    {!models.includes(settings.openai_model || 'gpt-4o-mini') && (
                      <option value={settings.openai_model || 'gpt-4o-mini'}>
                        {settings.openai_model || 'gpt-4o-mini'} (custom)
                      </option>
                    )}
                    {models.map(m => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={settings.openai_model || 'gpt-4o-mini'}
                    onChange={e => update('openai_model', e.target.value)}
                    placeholder="gpt-4o-mini"
                    className="flex-1 text-base rounded border border-gray-300 px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
                  />
                )}
                <button
                  onClick={fetchModels}
                  disabled={fetchingModels || !settings.openai_api_key}
                  className="text-sm px-3 py-2.5 rounded border border-gray-300 text-gray-600 hover:border-blue-400 hover:text-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                >
                  {fetchingModels ? '…' : 'Fetch models'}
                </button>
                {models.length > 0 && (
                  <button
                    onClick={() => setModels([])}
                    title="Switch to manual entry"
                    className="text-sm px-2.5 py-2.5 rounded border border-gray-300 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    ✎
                  </button>
                )}
              </div>
              {modelsError && <p className="text-sm text-red-600 mt-1">{modelsError}</p>}
              <p className="text-sm text-gray-400 mt-1">
                {models.length > 0
                  ? `${models.length} models available. Click ✎ to type a custom model name.`
                  : 'Default: gpt-4o-mini. Click "Fetch models" to see available options.'}
              </p>
            </div>

            <div>
              <label className="block text-base font-medium text-gray-700 mb-1.5">API Base URL (optional)</label>
              <input
                value={settings.openai_base_url || ''}
                onChange={e => update('openai_base_url', e.target.value)}
                placeholder="https://api.openai.com/v1"
                className="w-full text-base rounded border border-gray-300 px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <p className="text-sm text-gray-400 mt-1">
                Leave empty for OpenAI. Set to a custom URL for Azure, local models, etc.
              </p>
            </div>
          </div>

          {/* Manual translate button */}
          <div className="pt-3 border-t border-gray-100 space-y-2">
            <button
              onClick={handleTranslate}
              disabled={translating || !settings.openai_api_key || !settings.translation_target_language || settings.translation_target_language === 'None'}
              className="text-base px-4 py-2.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {translating ? 'Translating…' : 'Translate all untranslated words'}
            </button>
            {translateResult && (
              <p className="text-sm text-gray-600">{translateResult}</p>
            )}
          </div>
        </section>

        {/* ---- Save button ---- */}
        <div className="flex items-center gap-3 pt-6 border-t border-gray-200">
          <button
            onClick={save}
            disabled={saving}
            className="text-base px-6 py-2.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span className="text-sm text-green-600">✓ Saved</span>}
        </div>
      </div>
    </div>
  )
}
