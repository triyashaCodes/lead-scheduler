"use client";

import { useState, type ChangeEvent } from "react";

import { config } from "@/lib/config";
import { formatBytes } from "@/lib/format";

import formStyles from "./LeadForm.module.css";
import styles from "./ResumeField.module.css";

interface ResumeFieldProps {
  file: File | null;
  error?: string;
  onChange: (file: File) => void;
}

export function ResumeField({ file, error, onChange }: ResumeFieldProps) {
  const [dragging, setDragging] = useState(false);
  const hintId = "resume-hint";
  const errorId = "resume-error";

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const chosen = event.target.files?.[0];
    if (chosen) onChange(chosen);
    // Allow choosing the same file again after an error.
    event.target.value = "";
  }

  const classes = [
    styles.drop,
    dragging ? styles.dragging : "",
    file ? styles.filled : "",
    error ? styles.invalid : "",
  ].join(" ");

  return (
    <div className={formStyles.field}>
      <label htmlFor="resume" className={formStyles.label}>
        Resume
      </label>
      <div
        className={classes}
        onDragEnter={() => setDragging(true)}
        onDragOver={() => setDragging(true)}
        onDragLeave={() => setDragging(false)}
        onDrop={() => setDragging(false)}
      >
        <svg
          className={styles.glyph}
          viewBox="0 0 44 56"
          width="44"
          height="56"
          aria-hidden="true"
        >
          <path className={styles.sheet} d="M4 2h24l12 12v40H4z" />
          <path className={styles.fold} d="M28 2v12h12" />
          <path className={styles.lines} d="M11 28h22M11 35h16" />
          <path className={styles.check} d="M13 34l7 7 12-14" pathLength="1" />
        </svg>
        <div className={styles.text}>
          {file ? (
            <>
              <p className={styles.name}>{file.name}</p>
              <p id={hintId} className={styles.hint}>
                {formatBytes(file.size)}. Choose another file to replace it.
              </p>
            </>
          ) : (
            <>
              <p className={styles.name}>Drop your resume here or choose a file</p>
              <p id={hintId} className={styles.hint}>
                PDF, DOC or DOCX, up to {formatBytes(config.resumeMaxBytes)}
              </p>
            </>
          )}
        </div>
        <input
          id="resume"
          type="file"
          accept=".pdf,.doc,.docx"
          className={styles.input}
          onChange={handleChange}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
        />
      </div>
      {error && (
        <p id={errorId} className={formStyles.error}>
          {error}
        </p>
      )}
    </div>
  );
}
