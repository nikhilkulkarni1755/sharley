import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SealedColumn from "../components/SealedColumn";
import SpecView from "../components/SpecView";
import Tabs from "../components/Tabs";
import type { SealedTile, Spec } from "../lib/types";

describe("SealedColumn", () => {
  it("renders only index and family even if the payload carries secrets", () => {
    const leaky = [{ index: 1, family: "security", locked: true, code: "assert SECRET_CODE", name: "secret_name", hint: "secret_hint" }];
    const { container } = render(<SealedColumn tiles={leaky as SealedTile[]} results={{}} />);
    expect(container.textContent).not.toMatch(/SECRET_CODE|secret_name|secret_hint/);
    expect(screen.getByTestId("sealed-tile")).toHaveAttribute("data-state", "pending");
  });

  it("flips tiles by result", () => {
    render(<SealedColumn tiles={[{ index: 1, family: "env" }, { index: 2, family: "env" }]} results={{ 1: true, 2: false }} />);
    expect(screen.getAllByTestId("sealed-tile").map((t) => t.dataset.state)).toEqual(["passed", "failed"]);
  });
});

describe("SpecView", () => {
  const spec: Spec = {
    stack: "docker-api",
    requirements: [
      { id: "R1", text: "<img src=x onerror=alert(1)>", category: "security", evidence: { kind: "observed", source_span: "<script>x</script>", assumption_id: null } },
      { id: "R2", text: "inferred one", category: "functional", evidence: { kind: "inferred", source_span: null, assumption_id: "A1" } },
    ],
    assumptions: { A1: "notes are private" },
    ignored: [],
    coverage_pct: 75,
    spec_hash: "h",
  };

  it("shows both badge kinds with their evidence and renders markup as text", () => {
    const { container } = render(<SpecView spec={spec} busy={false} onGenerate={() => {}} />);
    expect(screen.getByText("observed")).toBeInTheDocument();
    expect(screen.getByText("inferred")).toBeInTheDocument();
    expect(screen.getByText(/A1: notes are private/)).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img, script")).toBeNull();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "75");
  });
});

describe("Tabs", () => {
  it("moves selection with arrow keys, Home and End", () => {
    const onChange = vi.fn();
    render(<Tabs active="intake" onChange={onChange} />);
    const intake = screen.getByRole("tab", { name: "Intake" });
    expect(intake).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(intake, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("judge");
    fireEvent.keyDown(intake, { key: "ArrowLeft" });
    expect(onChange).toHaveBeenLastCalledWith("playground");
    fireEvent.keyDown(intake, { key: "End" });
    expect(onChange).toHaveBeenLastCalledWith("eval");
    fireEvent.keyDown(intake, { key: "Home" });
    expect(onChange).toHaveBeenLastCalledWith("playground");
  });
});
