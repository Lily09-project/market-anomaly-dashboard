import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SymbolSearch, toSymbolOptions } from "./SymbolSearch";

const options = toSymbolOptions([
  { symbol: "0050", name: "元大台灣50", close: [90, 92.4] },
  { symbol: "2330", name: "台積電", close: [2150, 2145] },
  { symbol: "2317", name: "鴻海", close: [200, 200] },
]);

function setup(value = "0050", shortcut = false) {
  const onChange = vi.fn();
  render(
    <>
      <button type="button">elsewhere</button>
      <SymbolSearch options={options} value={value} label="標的" onChange={onChange} shortcut={shortcut} />
    </>,
  );
  return { onChange, user: userEvent.setup(), input: screen.getByRole("combobox", { name: "標的" }) };
}

describe("SymbolSearch", () => {
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("shows the current pick and opens the full list on focus", async () => {
    const { user, input } = setup();
    expect(input).toHaveValue("0050 元大台灣50");
    expect(input).toHaveAttribute("aria-expanded", "false");
    await user.click(input);
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(screen.getAllByRole("option")).toHaveLength(3);
    expect(screen.getByRole("option", { selected: true })).toHaveTextContent("0050");
  });

  it("filters as you type and picks with Enter", async () => {
    const { user, input, onChange } = setup();
    await user.click(input);
    await user.keyboard("台積");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await user.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith("2330");
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it("moves the active option with the arrow keys", async () => {
    const { user, input, onChange } = setup();
    await user.click(input);
    await user.keyboard("{ArrowDown}");
    const active = screen.getAllByRole("option")[1]!;
    expect(input).toHaveAttribute("aria-activedescendant", active.id);
    await user.keyboard("{ArrowUp}{ArrowUp}{Enter}");
    expect(onChange).toHaveBeenCalledWith("2317");
  });

  it("closes on Escape without changing the pick", async () => {
    const { user, input, onChange } = setup();
    await user.click(input);
    await user.keyboard("23{Escape}");
    expect(input).toHaveAttribute("aria-expanded", "false");
    expect(input).toHaveValue("0050 元大台灣50");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("says so when nothing matches", async () => {
    const { user, input } = setup();
    await user.click(input);
    await user.keyboard("9999");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByRole("status")).toHaveTextContent("找不到符合「9999」的標的");
  });

  it("picks with a click and remembers it as recent", async () => {
    const { user, input, onChange } = setup();
    await user.click(input);
    await user.click(screen.getByRole("option", { name: /2317/ }));
    expect(onChange).toHaveBeenCalledWith("2317");
    await user.click(screen.getByRole("button", { name: "elsewhere" }));
    await user.click(input);
    const first = screen.getAllByRole("option")[0]!;
    expect(first).toHaveTextContent("2317");
    expect(first).toHaveTextContent("最近");
  });

  it("shows each option's latest close and signed change", async () => {
    const { user, input } = setup();
    await user.click(input);
    const [etf, tsmc, flat] = screen.getAllByRole("option");
    expect(etf).toHaveTextContent("92.40");
    expect(etf).toHaveTextContent("+2.67%");
    expect(tsmc).toHaveTextContent("-0.23%");
    expect(flat!.querySelector("[data-sign]")).toHaveAttribute("data-sign", "0");
  });

  it("focuses on / only when the shortcut is on and the user is not typing elsewhere", async () => {
    const { user, input } = setup("0050", true);
    await user.click(screen.getByRole("button", { name: "elsewhere" }));
    await user.keyboard("/");
    expect(input).toHaveFocus();
    expect(input).toHaveValue("");
  });
});
