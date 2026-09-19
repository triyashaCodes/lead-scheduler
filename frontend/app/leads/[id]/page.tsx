import { LeadDetail } from "@/components/LeadDetail";

export default async function LeadPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LeadDetail id={id} />;
}
