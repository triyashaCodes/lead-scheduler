"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { AuthProvider, useAuth } from "./AuthProvider";
import styles from "./AttorneyShell.module.css";
import { GoogleSignIn } from "./GoogleSignIn";

function Header() {
  const { token, email, signOut } = useAuth();
  return (
    <header className={styles.bar}>
      <Link href="/leads" className={styles.brand}>
        Leads
      </Link>
      {token && (
        <div className={styles.account}>
          {email && <span className={styles.email}>{email}</span>}
          <button type="button" className={styles.signOut} onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}

function SignInPanel() {
  const { notice } = useAuth();
  return (
    <section className={styles.panel} aria-labelledby="sign-in-heading">
      <h1 id="sign-in-heading" className={styles.panelHeading}>
        Sign in to see leads
      </h1>
      <p className={styles.panelText}>
        Use the Google account you use for work. Only attorneys on the firm&apos;s
        list can get in.
      </p>
      {notice && (
        <p role="status" className={styles.notice}>
          {notice}
        </p>
      )}
      <GoogleSignIn />
    </section>
  );
}

function Gate({ children }: { children: ReactNode }) {
  const { ready, token } = useAuth();
  if (!ready) return null;
  return token ? <>{children}</> : <SignInPanel />;
}

export function AttorneyShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <Header />
      <main className={styles.main}>
        <Gate>{children}</Gate>
      </main>
    </AuthProvider>
  );
}
