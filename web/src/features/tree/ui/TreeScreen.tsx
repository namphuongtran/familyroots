'use client'

import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import type { TreePerson } from '@/domain/tree/tree'
import { useCapabilities } from '@/features/auth'
import { RelationshipEditorSheet } from '@/features/relationships'
import { List } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { useClientRequestContext } from '@/shared/http/context.client'
import { ApiError } from '@/shared/http/errors'
import { cn } from '@/lib/utils/cn'
import { useUIStore } from '@/store/ui.store'
import { useFamilyTree } from '../hooks/use-tree-queries'
import { treeKeys } from '../server/query-keys'
import { NodeActionsSheet, type NodeAction } from './NodeActionsSheet'
import { FocusPanel } from './FocusPanel'
import { TreeCanvas } from './TreeCanvas'
import { TreeListView } from './TreeListView'

/**
 * The tree page, spec § 7.4: the canvas over `GET /tree`, and the focus panel over
 * `GET /tree/focus/{id}` for the selected person. The depth comes from `useUIStore`, the one
 * client store. Query keys carry the clan id, so a clan switch refetches on its own.
 */
export function TreeScreen() {
  const t = useTranslations('tree')
  const { treeMaxGenerations } = useUIStore()
  const { context, ready, refreshAuth } = useClientRequestContext()
  const { data, isPending, isError, error, refetch } = useFamilyTree(
    { maxGenerations: treeMaxGenerations },
    { context, refreshAuth, enabled: ready },
  )
  const [selectedPersonId, setSelectedPersonId] = useState<string | null>(null)
  // Spec T-08: the list view is the canvas's accessible equivalent, over the same `GET /tree`.
  const [listMode, setListMode] = useState(false)
  // #328: the long-press sheet, and the relationship editor it opens.
  const [pressedId, setPressedId] = useState<string | null>(null)
  const [editor, setEditor] = useState<{ personId: string; action: NodeAction } | null>(null)
  const capabilities = useCapabilities()
  const queryClient = useQueryClient()
  const pressedName = pressedId && data ? nameIn(data.root, pressedId) : null

  const loading = !ready || isPending
  let body
  if (loading) {
    body = (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <Skeleton className="h-64 w-64 rounded-2xl" />
        <p role="status" className="text-muted-foreground text-sm">
          {t('loading')}
        </p>
      </div>
    )
  } else if (isError) {
    const noFounder = error instanceof ApiError && error.code === 'clan_founder_not_found'
    body = noFounder ? (
      <div className="flex h-full items-center justify-center p-4">
        <div className="bg-heritage-container text-heritage-container-foreground max-w-md space-y-2 rounded-2xl p-6">
          <h2 className="font-serif text-lg">{t('no_founder_title')}</h2>
          <p className="text-sm">{t('no_founder_body')}</p>
        </div>
      </div>
    ) : (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-4">
        <p className="text-muted-foreground text-sm">{t('load_error')}</p>
        <button
          type="button"
          onClick={() => void refetch()}
          className="text-primary text-sm font-medium hover:underline"
        >
          {t('retry')}
        </button>
      </div>
    )
  } else if (listMode) {
    body = <TreeListView root={data.root} onSelectPerson={setSelectedPersonId} />
  } else {
    body = (
      <TreeCanvas
        root={data.root}
        selectedPersonId={selectedPersonId}
        onSelectPerson={setSelectedPersonId}
        onLongPressPerson={setPressedId}
      />
    )
  }

  return (
    <div className="relative h-[calc(100vh-5rem)]">
      <div className="bg-background/80 absolute top-0 right-0 left-0 z-10 flex items-center justify-between px-4 py-2 backdrop-blur-xs">
        <h1 className="text-foreground font-serif text-lg">{t('page_title')}</h1>
        {/* Visible beside the canvas controls, never in a settings menu (spec T-08). */}
        <button
          type="button"
          aria-pressed={listMode}
          onClick={() => setListMode((on) => !on)}
          className={cn(
            'focus:ring-ring inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-medium focus:ring-2 focus:ring-offset-2 focus:outline-none',
            listMode
              ? 'bg-primary text-primary-foreground hover:bg-primary-hover'
              : 'bg-card text-foreground hover:bg-muted',
          )}
        >
          <List aria-hidden="true" className="h-4 w-4" />
          {t('list_view')}
        </button>
      </div>

      <section
        aria-label={t('page_title')}
        aria-busy={loading ? true : undefined}
        className="h-full pt-12"
      >
        {body}
      </section>

      {selectedPersonId && (
        <FocusPanel
          personId={selectedPersonId}
          onSelectPerson={setSelectedPersonId}
          onClose={() => setSelectedPersonId(null)}
        />
      )}

      {pressedId && (
        <NodeActionsSheet
          personId={pressedId}
          fullName={pressedName ?? ''}
          canAddRelationships={capabilities.createRelationship}
          onAction={(action) => {
            setEditor({ personId: pressedId, action })
            setPressedId(null)
          }}
          onClose={() => setPressedId(null)}
        />
      )}

      {editor && capabilities.createRelationship && (
        <RelationshipEditorSheet
          key={`${editor.personId}-${editor.action}`}
          personId={editor.personId}
          personName={data ? nameIn(data.root, editor.personId) : null}
          open
          onOpenChange={(open) => !open && setEditor(null)}
          initialSection={editor.action}
          // A new edge can move a node or add one, so the tree rereads.
          onChanged={() =>
            void queryClient.invalidateQueries({ queryKey: treeKeys.all(context.clanId) })
          }
        />
      )}
    </div>
  )
}

/** The name of the person, or spouse, with this id anywhere in the loaded tree. */
function nameIn(person: TreePerson, id: string): string | null {
  if (person.id === id) return person.fullName
  for (const spouse of person.spouses) if (spouse.id === id) return spouse.fullName
  for (const child of person.children) {
    const found = nameIn(child, id)
    if (found !== null) return found
  }
  return null
}
