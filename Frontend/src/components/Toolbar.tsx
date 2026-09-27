import { useEffect, useMemo, useRef, useState, type RefObject } from 'react'
import { useObjectState } from '../hooks/useObjectState'
import type { HistoryMap } from '../types'
import OrderHistory from './OrderHistory'
import { addAlert } from './alertSystem'
import { getFetchData } from './fetch'

export default function Toolbar({ historyItems, isUnorderedVisible, onCredentialsClick, onSearchChange, onUnorderedToggle, loadMealLists, searchInputRef, searchQuery }: {
  historyItems: HistoryMap
  isUnorderedVisible: boolean
  loadMealLists: () => Promise<void>
  onCredentialsClick: () => void
  onSearchChange: (value: string) => void
  onUnorderedToggle: () => void
  searchInputRef: RefObject<HTMLInputElement | null>
  searchQuery: string
}) {
  const [isOpen, setIsOpen, resetIsOpen] = useObjectState({ history: false, menu: false })
  const [isGathering, setIsGathering] = useState(false)
  const toolbarRef = useRef<HTMLDivElement | null>(null)
  const historyNotificationCount = useMemo(() => Object.keys(historyItems).length, [historyItems])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        searchInputRef.current?.focus()
        searchInputRef.current?.select()
      }
      if (event.key === 'Escape') onCredentialsClick()
    }
    document.addEventListener('keydown', handleKeyDown)

    return () => { document.removeEventListener('keydown', handleKeyDown) }
  })

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      if (!toolbarRef.current?.contains(event.target as Node)) resetIsOpen()
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') resetIsOpen()
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [resetIsOpen])

  async function handleGather() {
    if (isGathering) return
    setIsGathering(true)
    try {
      if (await getFetchData<unknown>('/api/gather') === null) return
      await loadMealLists()
      addAlert("Meals gathered", "G")
    }
    finally { setIsGathering(false) }
  }

  async function handleOrder() {
    if (await getFetchData<unknown>('/api/order') === null) return
    addAlert("Meals ordered", "G")
  }


  return <div className="app-toolbar" ref={toolbarRef}>
    <div className="toolbar-group">
      <button
        aria-expanded={isOpen.history}
        aria-haspopup="dialog"
        className="menu-button history-button"
        onClick={() => setIsOpen(open => ({ history: !open.history, menu: false }))}
        type="button"
      >
        Order history
        {historyNotificationCount > 0 && <span className="history-badge">{historyNotificationCount}</span>}
      </button>
      <input
        aria-label="Search meals"
        className="search-input"
        onChange={event => onSearchChange(event.target.value)}
        placeholder="Search"
        ref={searchInputRef}
        type="search"
        value={searchQuery}
      />
      {isOpen.history && <div className="menu-popup menu-popup-left" role="dialog" aria-label="Order history">
        <OrderHistory items={historyItems} />
      </div>}
    </div>
    <div className="toolbar-group toolbar-group-right">
      <button
        className="menu-button"
        onClick={onUnorderedToggle}
        type="button"
      >
        {isUnorderedVisible ? 'Hide Unordered' : 'Show Unordered'}
      </button>
      <button
        className="menu-button"
        onClick={() => {
          onCredentialsClick()
          resetIsOpen()
        }}
        type="button"
      >
        Credentials
      </button>
      <button
        aria-expanded={isOpen.menu}
        aria-haspopup="dialog"
        className="menu-button"
        onClick={() => setIsOpen(open => ({ history: false, menu: !open.menu }))}
        type="button"
      >
        User actions
      </button>
      {isOpen.menu && <div className="menu-popup menu-popup-right" role="dialog" aria-label="Actions menu">
        <button disabled={isGathering} type="button" onClick={handleGather}>
          {isGathering ? 'Gathering' : 'Gather'}
        </button>
        <button type="button" onClick={handleOrder}>Order</button>
      </div>}
    </div>
  </div>
}
