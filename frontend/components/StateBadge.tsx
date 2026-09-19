import type { LeadState } from "@/lib/types";

import styles from "./StateBadge.module.css";

const LABELS: Record<LeadState, string> = {
  PENDING: "Pending",
  REACHED_OUT: "Reached out",
};

export function StateBadge({ state }: { state: LeadState }) {
  return (
    <span className={state === "PENDING" ? styles.pending : styles.done}>
      {LABELS[state]}
    </span>
  );
}
