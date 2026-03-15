import { create } from "zustand";
import { fetchRecordingEntries } from "../api/sessions";
import type { RecordingEntryView } from "../api/types";

type PlaybackSpeed = 0.5 | 1 | 2 | 4;

interface ReplayState {
  entries: RecordingEntryView[];
  index: number;
  filter: string;
  limit: number;
  loading: boolean;
  error: string | null;
  playing: boolean;
  speed: PlaybackSpeed;

  load: (sessionId: string) => Promise<void>;
  setFilter: (filter: string) => void;
  setLimit: (limit: number) => void;
  setIndex: (index: number) => void;
  prev: () => void;
  next: () => void;
  first: () => void;
  last: () => void;
  setPlaying: (playing: boolean) => void;
  setSpeed: (speed: PlaybackSpeed) => void;
}

export const useReplayStore = create<ReplayState>((set, get) => ({
  entries: [],
  index: 0,
  filter: "",
  limit: 200,
  loading: false,
  error: null,
  playing: false,
  speed: 1,

  load: async (sessionId) => {
    const { filter, limit } = get();
    set({ loading: true, error: null, playing: false });
    try {
      const entries = await fetchRecordingEntries(sessionId, filter, limit);
      set({
        entries,
        index: entries.length > 0 ? entries.length - 1 : 0,
        loading: false,
      });
    } catch (err) {
      set({ error: String(err), loading: false });
    }
  },

  setFilter: (filter) => set({ filter }),
  setLimit: (limit) => set({ limit }),

  setIndex: (index) => {
    const { entries } = get();
    set({ index: Math.max(0, Math.min(index, entries.length - 1)) });
  },

  prev: () => {
    const { index } = get();
    if (index > 0) set({ index: index - 1 });
  },
  next: () => {
    const { index, entries } = get();
    if (index < entries.length - 1) set({ index: index + 1 });
  },
  first: () => set({ index: 0 }),
  last: () => {
    const { entries } = get();
    set({ index: Math.max(0, entries.length - 1) });
  },

  setPlaying: (playing) => set({ playing }),
  setSpeed: (speed) => set({ speed }),
}));
