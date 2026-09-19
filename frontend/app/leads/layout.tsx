import type { ReactNode } from "react";

import { AttorneyShell } from "@/components/AttorneyShell";

export const metadata = {
  title: "Leads",
  robots: { index: false, follow: false },
};

export default function LeadsLayout({ children }: { children: ReactNode }) {
  return <AttorneyShell>{children}</AttorneyShell>;
}
