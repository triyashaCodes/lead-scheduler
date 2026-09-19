"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, submitLead } from "@/lib/api";
import { config } from "@/lib/config";
import {
  validate,
  type FieldErrors,
  type FieldName,
  type FormValues,
} from "@/lib/validation";

import styles from "./LeadForm.module.css";
import { ResumeField } from "./ResumeField";

type Status = "idle" | "submitting" | "done";

const FIELD_ORDER: FieldName[] = ["first_name", "last_name", "email", "resume"];
const GENERIC_ERROR = "Something went wrong on our side. Try again in a moment.";

interface TextFieldProps {
  id: FieldName;
  label: string;
  type?: string;
  autoComplete: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
}

function TextField({
  id,
  label,
  type = "text",
  autoComplete,
  value,
  error,
  onChange,
}: TextFieldProps) {
  const errorId = `${id}-error`;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <input
        id={id}
        name={id}
        type={type}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={styles.input}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />
      {error && (
        <p id={errorId} className={styles.error}>
          {error}
        </p>
      )}
    </div>
  );
}

function focusFirstInvalid(errors: FieldErrors) {
  const first = FIELD_ORDER.find((name) => errors[name]);
  if (first) document.getElementById(first)?.focus();
}

export function LeadForm() {
  const [values, setValues] = useState<FormValues>({
    firstName: "",
    lastName: "",
    email: "",
  });
  const [resume, setResume] = useState<File | null>(null);
  const [website, setWebsite] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const confirmationRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (status === "done") confirmationRef.current?.focus();
  }, [status]);

  function clearError(name: FieldName) {
    const next = { ...errors, [name]: undefined };
    setErrors(next);
    // Drop the summary banner once nothing is left to fix.
    if (!FIELD_ORDER.some((field) => next[field])) setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (status === "submitting") return;

    const found = validate(values, resume, config.resumeMaxBytes);
    setErrors(found);
    if (Object.keys(found).length > 0 || !resume) {
      setFormError("Check the highlighted fields and try again.");
      focusFirstInvalid(found);
      return;
    }

    setFormError(null);
    setStatus("submitting");
    try {
      await submitLead({ ...values, resume, website });
      setStatus("done");
    } catch (error) {
      const apiError = error instanceof ApiError ? error : null;
      const fieldErrors = apiError?.fieldErrors ?? {};
      setErrors(fieldErrors);
      setFormError(apiError?.message ?? GENERIC_ERROR);
      setStatus("idle");
      focusFirstInvalid(fieldErrors);
    }
  }

  if (status === "done") {
    return (
      <div className={styles.sheet}>
        <h2 ref={confirmationRef} tabIndex={-1} className={styles.doneHeading}>
          Details sent
        </h2>
        <p className={styles.doneText}>
          A confirmation is on its way to {values.email.trim()}. An attorney will
          review your details and reach out.
        </p>
      </div>
    );
  }

  const submitting = status === "submitting";

  return (
    <form className={styles.sheet} onSubmit={handleSubmit} noValidate>
      <h2 className={styles.heading}>Your details</h2>

      <div className={styles.nameRow}>
        <TextField
          id="first_name"
          label="First name"
          autoComplete="given-name"
          value={values.firstName}
          error={errors.first_name}
          onChange={(firstName) => {
            setValues((v) => ({ ...v, firstName }));
            clearError("first_name");
          }}
        />
        <TextField
          id="last_name"
          label="Last name"
          autoComplete="family-name"
          value={values.lastName}
          error={errors.last_name}
          onChange={(lastName) => {
            setValues((v) => ({ ...v, lastName }));
            clearError("last_name");
          }}
        />
      </div>

      <TextField
        id="email"
        label="Email"
        type="email"
        autoComplete="email"
        value={values.email}
        error={errors.email}
        onChange={(email) => {
          setValues((v) => ({ ...v, email }));
          clearError("email");
        }}
      />

      <ResumeField
        file={resume}
        error={errors.resume}
        onChange={(file) => {
          setResume(file);
          clearError("resume");
        }}
      />

      {/* Honeypot: people never see or reach this; bots tend to fill it in. */}
      <div className={styles.trap} aria-hidden="true">
        <label>
          Website
          <input
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
          />
        </label>
      </div>

      {formError && (
        <p role="alert" className={styles.formError}>
          {formError}
        </p>
      )}

      <button
        type="submit"
        className={styles.submit}
        aria-disabled={submitting}
      >
        {submitting ? "Sending…" : "Send my details"}
      </button>
    </form>
  );
}
