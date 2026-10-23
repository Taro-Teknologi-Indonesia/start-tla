/**
 * The payment service provider (PSP). There is no transaction that spans the PSP
 * and our database, so every call carries an idempotency key: if we crash after
 * the call and the message comes again, the PSP answers the repeat without
 * charging twice. Real providers accept such a key on charges and refunds.
 */
export interface Psp {
  /** true: captured; false: declined. */
  charge(req: { key: string; amount: number }): Promise<boolean>;
  refund(req: { key: string; chargeKey: string }): Promise<void>;
}

/**
 * A stand-in provider for local runs: it declines charges above a limit and
 * captures the rest. Its answer depends only on the request, so a repeated
 * request gets the same answer, as a real provider gives for a repeated key.
 * Replace it with a client for your provider that passes `key` through.
 */
export class FakePsp implements Psp {
  constructor(private readonly declineAbove: number) {}

  async charge(req: { key: string; amount: number }): Promise<boolean> {
    return req.amount <= this.declineAbove;
  }

  async refund(_req: { key: string; chargeKey: string }): Promise<void> {}
}
