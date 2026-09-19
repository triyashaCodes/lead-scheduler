"use client";

import Script from "next/script";
import { useEffect, useRef, useState } from "react";

import { setToken } from "@/lib/auth";
import { config } from "@/lib/config";

export function GoogleSignIn() {
  const buttonRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ready || !buttonRef.current || !window.google) return;
    window.google.accounts.id.initialize({
      client_id: config.googleClientId,
      callback: (response) => setToken(response.credential),
    });
    window.google.accounts.id.renderButton(buttonRef.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
    });
  }, [ready]);

  return (
    <>
      <Script
        src="https://accounts.google.com/gsi/client"
        strategy="afterInteractive"
        onReady={() => setReady(true)}
      />
      <div ref={buttonRef} />
    </>
  );
}
