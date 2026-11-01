import { describe, expect, it } from 'vitest';
import { pinProblem } from './pin';

describe('pinProblem (mirrors the server policy)', () => {
  it.each(['1234', '123456', '654321', '890123', '111111', '121212', '112233', '123123', '12a456', '786786'])(
    'rejects weak PIN %s',
    (pin) => expect(pinProblem(pin)).not.toBeNull(),
  );
  it('accepts a random-looking PIN', () => expect(pinProblem('580317')).toBeNull());
  it('rejects PINs taken from the phone number', () => expect(pinProblem('456789', '9123456789')).not.toBeNull());
});
