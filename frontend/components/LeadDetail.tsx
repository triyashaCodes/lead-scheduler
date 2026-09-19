"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, downloadResume, getLead, markReachedOut } from "@/lib/api";
import { saveBlob } from "@/lib/download";
import { formatDateTime } from "@/lib/format";
import type { Lead } from "@/lib/types";

import buttons from "./buttons.module.css";
import styles from "./LeadDetail.module.css";
import { StateBadge } from "./StateBadge";

function messageOf(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function LeadDetail({ id }: { id: string }) {
  const [lead, setLead] = useState<Lead | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getLead(id)
      .then((result) => !cancelled && setLead(result))
      .catch((err) => !cancelled && setLoadError(messageOf(err)));
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function handleDownload() {
    if (downloading) return;
    setActionError(null);
    setDownloading(true);
    try {
      const { blob, filename } = await downloadResume(id);
      saveBlob(blob, filename);
    } catch (error) {
      setActionError(messageOf(error));
    } finally {
      setDownloading(false);
    }
  }

  async function handleMark() {
    if (marking) return;
    setActionError(null);
    setMarking(true);
    try {
      setLead(await markReachedOut(id));
    } catch (error) {
      setActionError(messageOf(error));
      if (error instanceof ApiError && error.status === 409) {
        // Show who got there first.
        getLead(id).then(setLead).catch(() => {});
      }
    } finally {
      setMarking(false);
    }
  }

  const back = (
    <Link href="/leads" className={styles.back}>
      Back to leads
    </Link>
  );

  if (loadError) {
    return (
      <>
        {back}
        <p role="alert" className={styles.error}>
          {loadError}
        </p>
      </>
    );
  }

  if (!lead) {
    return (
      <>
        {back}
        <p role="status" className={styles.muted}>
          Loading lead…
        </p>
      </>
    );
  }

  return (
    <>
      {back}
      <article className={styles.sheet}>
        <header className={styles.header}>
          <h1 className={styles.name}>
            {lead.first_name} {lead.last_name}
          </h1>
          <StateBadge state={lead.state} />
        </header>

        <dl className={styles.facts}>
          <div>
            <dt>Email</dt>
            <dd>
              <a href={`mailto:${lead.email}`}>{lead.email}</a>
            </dd>
          </div>
          <div>
            <dt>Submitted</dt>
            <dd>{formatDateTime(lead.created_at)}</dd>
          </div>
          {lead.state === "REACHED_OUT" && (
            <div>
              <dt>Reached out</dt>
              <dd>
                {lead.reached_out_at ? formatDateTime(lead.reached_out_at) : ""}
                {lead.reached_out_by ? ` by ${lead.reached_out_by}` : ""}
              </dd>
            </div>
          )}
        </dl>

        {actionError && (
          <p role="alert" className={styles.error}>
            {actionError}
          </p>
        )}

        <div className={styles.actions}>
          <button
            type="button"
            className={lead.state === "PENDING" ? buttons.secondary : buttons.primary}
            aria-disabled={downloading}
            onClick={handleDownload}
          >
            {downloading ? "Downloading…" : "Download resume"}
          </button>
          {lead.state === "PENDING" && (
            <button
              type="button"
              className={buttons.primary}
              aria-disabled={marking}
              onClick={handleMark}
            >
              {marking ? "Saving…" : "Mark reached out"}
            </button>
          )}
        </div>
      </article>
    </>
  );
}
