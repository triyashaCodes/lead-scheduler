"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ApiError, listLeads } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { LeadList, LeadState } from "@/lib/types";

import buttons from "./buttons.module.css";
import styles from "./LeadsList.module.css";
import { StateBadge } from "./StateBadge";

const PAGE_SIZE = 20;

const EMPTY_MESSAGES: Record<string, string> = {
  all: "No leads yet. New submissions will show up here.",
  PENDING: "No pending leads. Everyone has been contacted.",
  REACHED_OUT: "No leads have been marked as reached out yet.",
};

export function LeadsList({ state }: { state: LeadState | null }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<LeadList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const retry = useCallback(() => {
    setError(null);
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    listLeads({ state, page, pageSize: PAGE_SIZE })
      .then((result) => !cancelled && setData(result))
      .catch(
        (err) =>
          !cancelled &&
          setError(err instanceof ApiError ? err.message : "Something went wrong."),
      );
    return () => {
      cancelled = true;
    };
  }, [state, page, attempt]);

  if (error) {
    return (
      <div className={styles.message}>
        <p role="alert" className={styles.error}>
          {error}
        </p>
        <button type="button" className={buttons.secondary} onClick={retry}>
          Try again
        </button>
      </div>
    );
  }

  if (!data) {
    return (
      <p role="status" className={styles.muted}>
        Loading leads…
      </p>
    );
  }

  if (data.items.length === 0) {
    return <p className={styles.muted}>{EMPTY_MESSAGES[state ?? "all"]}</p>;
  }

  const first = (data.page - 1) * data.page_size + 1;
  const last = first + data.items.length - 1;

  return (
    <>
      <ul className={styles.list}>
        {data.items.map((lead) => (
          <li key={lead.id}>
            <Link href={`/leads/${lead.id}`} className={styles.row}>
              <span className={styles.name}>
                {lead.first_name} {lead.last_name}
              </span>
              <span className={styles.email}>{lead.email}</span>
              <span className={styles.date}>{formatDateTime(lead.created_at)}</span>
              <StateBadge state={lead.state} />
            </Link>
          </li>
        ))}
      </ul>
      <nav className={styles.pager} aria-label="Pages">
        <p className={styles.muted}>
          Showing {first}–{last} of {data.total}
        </p>
        <div className={styles.pagerButtons}>
          <button
            type="button"
            className={buttons.secondary}
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <button
            type="button"
            className={buttons.secondary}
            disabled={last >= data.total}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </div>
      </nav>
    </>
  );
}
