"use client";

import { useEffect, useRef, useState } from "react";
import { applyEvent, createStagger, emptyRun, isFinal } from "../lib/run";
import type { RunEvent } from "../lib/types";

const STAGGER_MS = 25;

/** Folds run events (replayed or streamed) into tile state, releasing them one by one so bursts animate. */
export function useRun() {
  const [state, setState] = useState(emptyRun);
  const [running, setRunning] = useState(false);
  const [stagger] = useState(() =>
    createStagger<RunEvent>((event) => {
      setState((s) => applyEvent(s, event));
      if (isFinal(event)) setRunning(false);
    }, STAGGER_MS),
  );
  const stop = useRef<() => void>(() => {});

  useEffect(() => () => {
    stop.current();
    stagger.clear();
  }, [stagger]);

  const begin = () => {
    stop.current();
    stagger.clear();
    setState(emptyRun);
    setRunning(true);
  };

  return {
    state,
    running,
    play(events: RunEvent[]) {
      begin();
      events.forEach(stagger.push);
    },
    stream(open: (onEvent: (e: RunEvent) => void) => () => void) {
      begin();
      stop.current = open(stagger.push);
    },
  };
}
