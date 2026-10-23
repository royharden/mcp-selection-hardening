"""One exact repeat/transport decision rule shared by pilot and full development."""

from fractions import Fraction


def repeat_rule(*, invalid: int, outputs: int, failures: int, attempts: int,
                successes: int, known_utility: int) -> dict:
    if (any(type(n) is not int or n < 0 for n in
            (invalid, outputs, failures, attempts, successes, known_utility))
            or invalid > outputs or failures > attempts or successes > known_utility):
        raise ValueError("invalid repeat-rule counters")
    invalidity = Fraction(invalid, outputs) if outputs else None
    transport = Fraction(failures, attempts) if attempts else None
    variance = (Fraction(successes * (known_utility - successes), known_utility ** 2)
                if known_utility >= 2 else None)
    return {
        "semantic_invalid_rate": None if invalidity is None else float(invalidity),
        "transport_failure_rate": None if transport is None else float(transport),
        "bernoulli_utility_variance": None if variance is None else float(variance),
        "proposes_five_repeats": bool((invalidity is not None and invalidity > Fraction(1, 10))
                                     or (variance is not None and variance > Fraction(1, 5))),
        "requires_transport_repair": bool(transport is not None and transport > Fraction(1, 20)),
    }
