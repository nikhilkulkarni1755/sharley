"use client";

import { useEffect, useState } from "react";
import { getDemo, getHealth } from "../lib/api";
import type { Bank, Demo, Health } from "../lib/types";
import Eval from "./Eval";
import ErrorNote from "./ErrorNote";
import Header from "./Header";
import Intake from "./Intake";
import Judge, { type Mode } from "./Judge";
import Playground from "./Playground";
import Tabs, { type TabId } from "./Tabs";

export default function Board() {
  const [tab, setTab] = useState<TabId>("playground");
  const [mode, setMode] = useState<Mode>("replay");
  const [bank, setBank] = useState<Bank | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [demo, setDemo] = useState<Demo | null>(null);
  const [demoError, setDemoError] = useState<string | null>(null);

  const fetchDemo = () => getDemo().then(setDemo, (e: Error) => setDemoError(e.message));

  const retryDemo = () => {
    setDemoError(null);
    void fetchDemo();
  };

  useEffect(() => {
    getHealth().then(setHealth, () => setHealth(null));
    void fetchDemo();
  }, []);

  const bankReady = (b: Bank) => {
    setBank(b);
    setMode("live");
    setTab("judge");
  };

  return (
    <main>
      <Header health={health} />
      <Tabs active={tab} onChange={setTab} />
      <section role="tabpanel" id="panel-playground" aria-labelledby="tab-playground" hidden={tab !== "playground"}>
        {tab === "playground" && <Playground />}
      </section>
      <section role="tabpanel" id="panel-intake" aria-labelledby="tab-intake" hidden={tab !== "intake"}>
        <Intake onBank={bankReady} />
      </section>
      <section role="tabpanel" id="panel-judge" aria-labelledby="tab-judge" hidden={tab !== "judge"}>
        <Judge key={`${mode}:${bank?.key}`} mode={mode} onMode={setMode} liveBank={bank} demo={demo} loadError={demoError} onRetry={retryDemo} />
      </section>
      <section role="tabpanel" id="panel-eval" aria-labelledby="tab-eval" hidden={tab !== "eval"}>
        {demo ? <Eval demo={demo} /> : demoError ? <ErrorNote message={demoError} onRetry={retryDemo} /> : <p className="muted">Loading demo…</p>}
      </section>
    </main>
  );
}
