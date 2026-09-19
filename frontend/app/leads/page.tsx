import Link from "next/link";

import { LeadsList } from "@/components/LeadsList";
import type { LeadState } from "@/lib/types";

import styles from "./page.module.css";

const FILTERS: { label: string; state: LeadState | null; href: string }[] = [
  { label: "All", state: null, href: "/leads" },
  { label: "Pending", state: "PENDING", href: "/leads?state=PENDING" },
  { label: "Reached out", state: "REACHED_OUT", href: "/leads?state=REACHED_OUT" },
];

function parseState(value: string | undefined): LeadState | null {
  return value === "PENDING" || value === "REACHED_OUT" ? value : null;
}

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string }>;
}) {
  const state = parseState((await searchParams).state);

  return (
    <>
      <h1 className={styles.heading}>Leads</h1>
      <nav aria-label="Filter leads">
        <ul className={styles.filters}>
          {FILTERS.map((filter) => (
            <li key={filter.label}>
              <Link
                href={filter.href}
                className={styles.filter}
                aria-current={filter.state === state ? "page" : undefined}
              >
                {filter.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <LeadsList key={state ?? "all"} state={state} />
    </>
  );
}
