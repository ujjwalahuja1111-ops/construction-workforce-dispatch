import { ShiftStateT, ShiftState } from '../types/domain';
import { AppError } from '../utils/errors';

/**
 * ShiftEngine - deterministic state machine.
 *
 * The full lifecycle graph (linear, with CANCELLED as a terminal branch):
 *
 *   CREATED → OFFERED → ACCEPTED → TRAVELLING → ARRIVED → CHECKED_IN
 *         → WORKING ⇄ BREAK ⇄ RESUMED → COMPLETED → CHECKED_OUT → CLOSED
 *
 * CANCELLED can be reached from any non-terminal state (contractor cancels
 * job / worker no-shows). CLOSED is terminal.
 */

const TRANSITIONS: Record<ShiftStateT, ShiftStateT[]> = {
  CREATED:      ['OFFERED', 'CANCELLED'],
  OFFERED:      ['ACCEPTED', 'CANCELLED'],
  ACCEPTED:     ['TRAVELLING', 'CANCELLED'],
  TRAVELLING:   ['ARRIVED', 'CANCELLED'],
  ARRIVED:      ['CHECKED_IN', 'CANCELLED'],
  CHECKED_IN:   ['WORKING', 'CANCELLED'],
  WORKING:      ['BREAK', 'COMPLETED', 'CANCELLED'],
  BREAK:        ['RESUMED', 'CANCELLED'],
  RESUMED:      ['WORKING', 'BREAK', 'COMPLETED', 'CANCELLED'],
  COMPLETED:    ['CHECKED_OUT'],
  CHECKED_OUT:  ['CLOSED'],
  CLOSED:       [],
  CANCELLED:    [],
};

export class ShiftEngine {
  static canTransition(from: ShiftStateT, to: ShiftStateT): boolean {
    return TRANSITIONS[from]?.includes(to) ?? false;
  }

  static assertTransition(from: ShiftStateT, to: ShiftStateT): void {
    if (!this.canTransition(from, to)) {
      throw AppError.invalidState(
        `Illegal shift transition: ${from} → ${to}`,
      );
    }
  }

  static isTerminal(s: ShiftStateT): boolean {
    return s === ShiftState.CLOSED || s === ShiftState.CANCELLED;
  }
}
