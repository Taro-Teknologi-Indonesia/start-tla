---------------------------- MODULE Counter ----------------------------
(* A bounded counter: a minimal spec to verify your setup works. *)
EXTENDS Naturals

CONSTANT Max
VARIABLE count

Init == count = 0

Increment == count < Max /\ count' = count + 1
Reset     == count = Max /\ count' = 0

Next == Increment \/ Reset

Spec == Init /\ [][Next]_count

TypeOK == count \in 0..Max
=============================================================================
