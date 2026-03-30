//
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
// SPDX-License-Identifier: AGPL-3.0-or-later
//

export interface DeckMuxUser {
  userId: string;
  name: string;
  color: string;
  role: string;
  initials: string;
  scrollLine: number;
  scrollRange: [number, number];
  selection: { start: { line: number; col: number }; end: { line: number; col: number } } | null;
  pin: { line: number } | null;
  typing: boolean;
  queuedKeys: string;
  isOwner: boolean;
}

export interface DeckMuxConfig {
  autoTransferIdleS: number;
  keystrokeQueue: "display" | "replay";
}

export interface ContextAction {
  icon: string;
  label: string;
  sublabel?: string;
  danger?: boolean;
  onClick: () => void;
}
