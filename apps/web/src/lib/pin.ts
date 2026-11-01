// PIN rules, mirrored from services/api/app/security.py `pin_problem` (the server is the source of truth).

export const PIN_MIN = 6;
export const PIN_MAX = 12;

const COMMON = new Set([
  '123123', '121212', '112233', '123321', '654321', '111222', '112211', '131313', '159753', '147258',
  '258456', '102030', '101010', '100200', '200000', '786786', '007007', '123654', '147852', '696969',
  '520520', '520131', '123456789', '1234567890', '0123456789', '123412', '232323', '202020', '212121',
]);

/** Hindi reason why `pin` is too weak, or null when it is acceptable. */
export function pinProblem(pin: string, phone = ''): string | null {
  if (!/^\d+$/.test(pin)) return 'The PIN must contain digits only.';
  if (pin.length < PIN_MIN || pin.length > PIN_MAX) return `The PIN must be ${PIN_MIN} to ${PIN_MAX} digits long.`;
  if (new Set(pin).size <= 2) return 'The PIN must have at least 3 different digits (not like 111111 or 121212).';
  const steps = new Set<number>();
  for (let i = 1; i < pin.length; i++) steps.add((Number(pin[i]) - Number(pin[i - 1]) + 10) % 10);
  if (steps.size === 1 && (steps.has(1) || steps.has(9))) return 'A sequential PIN (like 123456 or 987654) is easy to guess.';
  const half = pin.slice(0, Math.floor(pin.length / 2));
  if (COMMON.has(pin) || half + half === pin) return 'This PIN is too common. Choose another one.';
  const digits = phone.replace(/\D/g, '');
  if (digits && (digits.includes(pin) || pin.includes(digits.slice(-PIN_MIN)))) return 'Do not use your mobile number in the PIN.';
  return null;
}
