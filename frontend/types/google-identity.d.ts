// The small part of Google Identity Services this app uses.
interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleIdentity {
  accounts: {
    id: {
      initialize(options: {
        client_id: string;
        callback: (response: GoogleCredentialResponse) => void;
        auto_select?: boolean;
      }): void;
      renderButton(
        parent: HTMLElement,
        options: {
          type?: "standard";
          theme?: "outline" | "filled_blue" | "filled_black";
          size?: "large" | "medium" | "small";
          text?: "signin_with" | "signin" | "continue_with";
          shape?: "rectangular" | "pill";
          width?: number;
        },
      ): void;
      disableAutoSelect(): void;
    };
  };
}

interface Window {
  google?: GoogleIdentity;
}
