//
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 MindTenet LLC. All rights reserved.
// SPDX-License-Identifier: AGPL-3.0-or-later
//
import { afterEach, describe, expect, it, vi } from "vitest";
import { mountHijackWidget } from "./hijack-widget-host.js";

describe("mountHijackWidget", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("returns mounted=false with error when UndefHijack is not available", () => {
    // Ensure UndefHijack is not on window
    vi.stubGlobal("window", { UndefHijack: undefined });
    const container = document.createElement("div");
    const result = mountHijackWidget(container, "sess-1", "operator");
    expect(result.mounted).toBe(false);
    expect(result.error).toBe("UndefHijack is not available");
  });

  it("returns mounted=true when UndefHijack is a function", () => {
    const MockHijack = vi.fn();
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    (window as any).UndefHijack = MockHijack;
    const container = document.createElement("div");
    document.body.appendChild(container);
    const result = mountHijackWidget(container, "sess-1", "operator");
    expect(result.mounted).toBe(true);
    expect(result.error).toBeNull();
  });

  it("calls UndefHijack constructor with correct config for operator surface", () => {
    const MockHijack = vi.fn();
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    (window as any).UndefHijack = MockHijack;
    const container = document.createElement("div");
    mountHijackWidget(container, "my-session", "operator");
    expect(MockHijack).toHaveBeenCalledWith(container, {
      workerId: "my-session",
      showAnalysis: true,
      mobileKeys: true,
    });
  });

  it("calls UndefHijack constructor with correct config for user surface", () => {
    const MockHijack = vi.fn();
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    (window as any).UndefHijack = MockHijack;
    const container = document.createElement("div");
    mountHijackWidget(container, "my-session", "user");
    expect(MockHijack).toHaveBeenCalledWith(container, {
      workerId: "my-session",
      showAnalysis: false,
      mobileKeys: false,
    });
  });

  it("calls UndefHijack constructor with correct config for undefined surface", () => {
    const MockHijack = vi.fn();
    // biome-ignore lint/suspicious/noExplicitAny: test mock
    (window as any).UndefHijack = MockHijack;
    const container = document.createElement("div");
    mountHijackWidget(container, "sess", undefined);
    expect(MockHijack).toHaveBeenCalledWith(container, {
      workerId: "sess",
      showAnalysis: false,
      mobileKeys: false,
    });
  });
});
