import { LeadForm } from "@/components/LeadForm";

import styles from "./page.module.css";

export default function ApplyPage() {
  return (
    <main className={styles.page}>
      <h1 className={styles.headline}>
        Tell us who you are. An attorney will take it from here.
      </h1>
      <div className={styles.form}>
        <LeadForm />
      </div>
      <section className={styles.next} aria-labelledby="next-heading">
        <h2 id="next-heading" className={styles.nextHeading}>
          What happens next
        </h2>
        <ol className={styles.steps}>
          <li>Send your name, email and resume.</li>
          <li>You get a confirmation by email right away.</li>
          <li>An attorney reviews your details and reaches out.</li>
        </ol>
      </section>
    </main>
  );
}
