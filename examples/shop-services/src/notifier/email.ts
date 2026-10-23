/**
 * The email provider. Sending an email and recording it in our inbox are two
 * systems, so a crash in between sends the email again on the next delivery,
 * inbox or not. The idempotency key closes that gap ("email_key" in the spec):
 * the provider sends at most one email per key.
 */
export interface EmailProvider {
  send(email: { key: string; orderId: string; subject: string; text: string }): Promise<void>;
}

/** For local runs: prints the email. Swap in your provider's client, passing `key` as its idempotency key. */
export class ConsoleEmail implements EmailProvider {
  async send(email: { key: string; orderId: string; subject: string; text: string }): Promise<void> {
    console.log(`email [${email.key}] ${email.subject}: ${email.text}`);
  }
}
