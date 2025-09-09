'use client';

import React, { useEffect } from 'react';

import { InterventionsTable, InterventionData } from '@/components/search/interventions-table';
import { useAPI, getThematicGroupItems as getThematicGroupItemsExternal } from '@/lib/api';
import EvidenceIssuesTable from '@/components/v2/evidence/EvidenceIssuesTable';
import type { EvidenceItem } from '@/lib/evidenceStore';

type ItemsListViewProps = {
  projectId: string;
  themeId: number;
  themeType: 'intervention' | 'issue';
};

export default function ItemsListView({ projectId, themeId, themeType }: ItemsListViewProps) {
  const { getProjectInterventions } = useAPI();
  const [allInterventions, setAllInterventions] = React.useState<InterventionData[] | null>(null);
  const [loadingAgg, setLoadingAgg] = React.useState(false);
  const [items, setItems] = React.useState<EvidenceItem[]>([]);
  const [isLoadingItems, setIsLoadingItems] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!projectId || !themeId) return;
      setIsLoadingItems(true);
      setError(null);
      try {
        const res = await getThematicGroupItemsExternal(projectId, String(themeId), themeType);
        if (!cancelled) setItems(res as EvidenceItem[]);
      } catch (e: unknown) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : 'Failed to load items';
          setError(msg);
        }
      } finally {
        if (!cancelled) setIsLoadingItems(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [projectId, themeId, themeType]);

  // Load aggregated interventions once per project when viewing intervention themes
  useEffect(() => {
    let cancelled = false;
    const loadAgg = async () => {
      if (!projectId || themeType !== 'intervention') return;
      // Avoid reloading if already present
      if (allInterventions && allInterventions.length > 0) return;
      setLoadingAgg(true);
      try {
        const resp = await getProjectInterventions(projectId);
        if (!cancelled) setAllInterventions(resp.interventions || []);
      } catch {
        if (!cancelled) setAllInterventions([]);
      } finally {
        if (!cancelled) setLoadingAgg(false);
      }
    };
    loadAgg();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, themeType]);

  const filteredInterventions = React.useMemo(() => {
    if (themeType !== 'intervention') return [] as InterventionData[];
    if (!allInterventions) return [] as InterventionData[];
    const titles = new Set(items.map((it) => (it?.title || '').toLowerCase().trim()));
    return (allInterventions || []).filter((iv) => titles.has((iv.name || '').toLowerCase().trim()));
  }, [allInterventions, items, themeType]);

  // For issues, use the rich EvidenceItem objects returned by the items endpoint
  const issuesForTheme = React.useMemo(() => {
    if (themeType !== 'issue') return [] as EvidenceItem[];
    // Deduplicate by normalised title + document id (if available). Merge supporting_evidence.
    const normalise = (s: unknown) => String(s || '').trim().replace(/\s+/g, ' ').toLowerCase();
    const byKey = new Map<string, EvidenceItem>();
    for (const it of items) {
      const titleKey = normalise(it?.title);
      const docId = it?.document?.doc_id ? String(it.document.doc_id) : '';
      const key = `${titleKey}::${docId}`;
      if (!byKey.has(key)) {
        // clone to avoid mutating original
        const clone = { ...it, supporting_evidence: Array.isArray(it.supporting_evidence) ? [...it.supporting_evidence] : [] } as EvidenceItem;
        byKey.set(key, clone);
      } else {
        const existing = byKey.get(key) as EvidenceItem;
        // merge supporting evidence uniquely
        const merged = new Set<string>(
          ([] as string[])
            .concat(existing.supporting_evidence || [])
            .concat(Array.isArray(it.supporting_evidence) ? it.supporting_evidence : [])
            .map((s) => String(s || ''))
        );
        existing.supporting_evidence = Array.from(merged).filter((s) => s.trim().length > 0);
      }
    }
    return Array.from(byKey.values());
  }, [items, themeType]);

  // Ant Design table columns removed in favour of card grid view

  return (
    <div className="w-full">
      {error && <div className="text-red-500 text-sm">{String(error)}</div>}

      {themeType === 'intervention' ? (
        (isLoadingItems || loadingAgg) ? (
          <div className="text-sm text-muted-foreground">Loading interventions…</div>
        ) : filteredInterventions && filteredInterventions.length > 0 ? (
          <InterventionsTable interventions={filteredInterventions} />
        ) : (
          <div className="text-sm text-muted-foreground">No interventions found for this theme.</div>
        )
      ) : (isLoadingItems) ? (
        <div className="text-sm text-muted-foreground">Loading key issues…</div>
      ) : issuesForTheme && issuesForTheme.length > 0 ? (
        <EvidenceIssuesTable issues={issuesForTheme} />
      ) : (
        <div className="text-sm text-muted-foreground">No key issues found for this theme.</div>
      )}
    </div>
  );
}


