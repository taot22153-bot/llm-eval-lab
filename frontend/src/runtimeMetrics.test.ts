import { describe, expect, it } from "vitest";

import { formatCostUsd } from "./runtimeMetrics";

describe("formatCostUsd", () => {
  it("distinguishes unknown, zero, small positive, and ordinary costs", () => {
    expect(formatCostUsd(null)).toBe("Unknown");
    expect(formatCostUsd(0)).toBe("$0.0000");
    expect(formatCostUsd(0.0000275)).toBe("<$0.0001");
    expect(formatCostUsd(0.01234)).toBe("$0.0123");
  });
});
