import { useEffect } from 'react'
import { useStore } from '../store/useStore'

export function AnkiStatus() {
  const {
    ankiStatus, checkAnkiStatus,
    syncing, syncToAnki, lastSyncResult,
    autoSync, setAutoSync,
  } = useStore()

  useEffect(() => {
    checkAnkiStatus()
    const id = setInterval(checkAnkiStatus, 15_000)
    return () => clearInterval(id)
  }, [checkAnkiStatus])

  const connected = ankiStatus?.connected ?? false

  return (
    <div className="flex items-center gap-4 flex-wrap">
      {/* Connection dot */}
      <div className="flex items-center gap-2 text-base">
        <span
          className={`inline-block w-3 h-3 rounded-full ${
            ankiStatus === null ? 'bg-gray-300' : connected ? 'bg-green-500' : 'bg-red-400'
          }`}
        />
        <span className="text-gray-500">
          {ankiStatus === null
            ? 'Checking…'
            : connected
            ? `Anki connected (v${ankiStatus.version})`
            : 'Anki not running'}
        </span>
      </div>

      {/* Auto-sync toggle */}
      <label className="flex items-center gap-2 cursor-pointer select-none text-base text-gray-500">
        <span
          onClick={() => setAutoSync(!autoSync)}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            autoSync ? 'bg-blue-500' : 'bg-gray-300'
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              autoSync ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </span>
        Auto-sync
      </label>

      {/* Manual sync button */}
      <button
        onClick={syncToAnki}
        disabled={syncing || !connected}
        className="px-4 py-1.5 text-base rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
      >
        {syncing ? 'Syncing…' : 'Sync to Anki'}
      </button>

      {/* Last sync result */}
      {lastSyncResult && (
        <span className="text-sm text-gray-400">
          Last sync: {lastSyncResult.synced} synced
          {lastSyncResult.failed > 0 && `, ${lastSyncResult.failed} failed`}
        </span>
      )}
    </div>
  )
}
