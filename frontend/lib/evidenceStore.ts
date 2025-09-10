import { create } from 'zustand';
import { getThematicGroups, getThematicGroupItems } from './api';

export type ThematicGroup = {
  id: number;
  theme_title: string;
  theme_summary: string;
  item_count: number;
};

export type Outcome = {
  outcome: string;
  direction_of_effect: string;
  effect_size?: string;
  significance?: string;
};

export type EvidenceItem = {
  id: number | string;
  title: string;
  brief_description?: string;
  frequency?: number;
  outcomes: Outcome[];
  supporting_evidence: string[];
  countries: string[];
  document?: {
    doc_id?: string;
    title?: string;
    source?: string;
    landing_page_url?: string;
    year?: number;
    venue?: string;
    source_type?: string;
    source_country?: string;
  };
};

type ActiveTab = 'intervention' | 'issue';

export interface EvidenceState {
  // Data
  interventionThematicGroups: ThematicGroup[];
  issueThematicGroups: ThematicGroup[];
  interventions: EvidenceItem[];
  keyIssues: EvidenceItem[];

  // UI state
  activeTab: ActiveTab;
  isLoadingGroups: boolean;
  isLoadingItems: boolean;
  error: string | null;

  // Actions
  fetchThematicGroups: (projectId: string, themeType: 'intervention' | 'issue') => Promise<void>;
  fetchItemsForTheme: (
    projectId: string,
    themeId: number,
    itemType: ActiveTab,
  ) => Promise<void>;
  setActiveTab: (tab: ActiveTab) => void;
}

export const useEvidenceStore = create<EvidenceState>((set) => ({
  // Initial state
  interventionThematicGroups: [],
  issueThematicGroups: [],
  interventions: [],
  keyIssues: [],
  activeTab: 'intervention',
  isLoadingGroups: false,
  isLoadingItems: false,
  error: null,

  // Actions
  async fetchThematicGroups(projectId: string, themeType: 'intervention' | 'issue') {
    set({ isLoadingGroups: true, error: null });
    try {
      const groups = await getThematicGroups(projectId, themeType);
      if (themeType === 'intervention') {
        set({ interventionThematicGroups: groups, isLoadingGroups: false });
      } else {
        set({ issueThematicGroups: groups, isLoadingGroups: false });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load thematic groups';
      set({ error: message, isLoadingGroups: false });
    }
  },

  async fetchItemsForTheme(projectId: string, themeId: number, itemType: ActiveTab) {
    set({ isLoadingItems: true, error: null, interventions: [], keyIssues: [] });
    try {
      const items = await getThematicGroupItems(
        projectId,
        String(themeId),
        itemType,
      );
      if (itemType === 'intervention') {
        set({ interventions: items as EvidenceItem[], isLoadingItems: false });
      } else {
        set({ keyIssues: items as EvidenceItem[], isLoadingItems: false });
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load items for theme';
      set({ error: message, isLoadingItems: false });
    }
  },

  setActiveTab(tab: ActiveTab) {
    set({ activeTab: tab });
  },
}));