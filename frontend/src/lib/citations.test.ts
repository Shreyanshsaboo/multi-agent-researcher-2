import { describe, expect, it } from "vitest";

import { citationOrder } from "./citations";

describe("citationOrder", () => {
  it("lists each cited source once, in order of first citation", () => {
    expect(citationOrder("Costs fell [E3][E1]. Latency rose [E1]. See [E2].")).toEqual(["E3", "E1", "E2"]);
  });

  it("ignores citations that are already links", () => {
    expect(citationOrder("[E1](https://example.com) and [E2]")).toEqual(["E2"]);
  });
});
