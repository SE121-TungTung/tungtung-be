"""Computerized Adaptive Testing (CAT) Engine with 3PL Item Response Theory (IRT).

Implements:
1. 3-Parameter Logistic (3PL) model for probability and Fisher information.
2. Bayesian Expected A Posteriori (EAP) estimation for early items and edge cases (all correct/all wrong).
3. Maximum Likelihood Estimation (MLE) via Newton-Raphson with step-limiting and domain clamping.
4. Fisher Information maximization for next question selection.
5. Conversion from theta logit scale to estimated IELTS Band.
6. Stopping condition verification (SE threshold or max items).
"""

import math
from typing import Dict, List, Optional, Tuple, Any


# Default configuration
DEFAULT_CLAMP_RANGE: Tuple[float, float] = (-4.0, 4.0)
DEFAULT_SE_THRESHOLD: float = 0.30
DEFAULT_MAX_ITEMS: int = 20
DEFAULT_MIN_ITEMS: int = 5
EAP_THRESHOLD_ITEMS: int = 5


def p_correct(theta: float, a: float, b: float, c: float) -> float:
    """Calculate probability of a correct response under the 3PL IRT model.

    P(theta) = c + (1 - c) / (1 + exp(-a * (theta - b)))

    Args:
        theta: Latent ability parameter (typically in [-4.0, 4.0]).
        a: Discrimination parameter (typically in [0.5, 2.5]).
        b: Difficulty parameter (typically in [-3.0, 3.0]).
        c: Guessing / pseudo-chance parameter (typically in [0.0, 0.5]).

    Returns:
        float: Probability of correct response in [c, 1.0].
    """
    z = a * (theta - b)
    if z < -40.0:
        return float(c)
    if z > 40.0:
        return 1.0
    exp_term = math.exp(-z)
    return float(c + (1.0 - c) / (1.0 + exp_term))


def fisher_information(theta: float, a: float, b: float, c: float) -> float:
    """Calculate Fisher Information I(theta) for a single item under 3PL.

    I(theta) = (P'(theta))^2 / (P(theta) * (1 - P(theta)))
    where P'(theta) = a * (P - c) * (1 - P) / (1 - c).

    Args:
        theta: Latent ability.
        a: Discrimination parameter.
        b: Difficulty parameter.
        c: Guessing parameter.

    Returns:
        float: Fisher information >= 0.0.
    """
    p = p_correct(theta, a, b, c)
    q = 1.0 - p
    denom_c = 1.0 - c
    if denom_c <= 0.0 or p * q <= 1e-12:
        return 0.0

    p_prime = a * (p - c) * q / denom_c
    info = (p_prime ** 2) / (p * q)
    return max(0.0, float(info))


def estimate_theta_eap(
    responses: List[Dict[str, Any]],
    prior_mean: float = 0.0,
    prior_sd: float = 1.0,
    quad_points: int = 41,
    clamp_range: Tuple[float, float] = DEFAULT_CLAMP_RANGE
) -> Tuple[float, float]:
    """Bayesian Expected A Posteriori (EAP) ability estimation.

    Numerically stable against all-correct or all-wrong response vectors.
    Uses standard normal prior over the quadrature grid.

    Args:
        responses: List of dicts with 'a', 'b', 'c', 'is_correct'.
        prior_mean: Prior mean of ability distribution (default 0.0).
        prior_sd: Prior standard deviation (default 1.0).
        quad_points: Number of quadrature grid points (default 41).
        clamp_range: Min and max bounds for theta (default [-4.0, 4.0]).

    Returns:
        Tuple[float, float]: (estimated_theta, standard_error).
    """
    if not responses:
        return prior_mean, prior_sd

    lower, upper = clamp_range
    step = (upper - lower) / (quad_points - 1)
    grid = [lower + i * step for i in range(quad_points)]

    # Compute unnormalized log-prior for stability
    log_priors = [
        -0.5 * ((theta - prior_mean) / prior_sd) ** 2
        for theta in grid
    ]

    # Compute log-likelihood for each quadrature point
    log_posteriors = []
    for theta, log_prior in zip(grid, log_priors):
        log_lik = 0.0
        for r in responses:
            p = p_correct(theta, float(r["a"]), float(r["b"]), float(r["c"]))
            p = min(max(p, 1e-10), 1.0 - 1e-10)
            if r["is_correct"]:
                log_lik += math.log(p)
            else:
                log_lik += math.log(1.0 - p)
        log_posteriors.append(log_prior + log_lik)

    # Softmax normalization for numerical stability
    max_log_post = max(log_posteriors)
    weights = [math.exp(lp - max_log_post) for lp in log_posteriors]
    total_weight = sum(weights)

    if total_weight <= 0.0:
        return prior_mean, prior_sd

    normalized_weights = [w / total_weight for w in weights]

    # EAP estimate: mean of posterior
    theta_eap = sum(theta * w for theta, w in zip(grid, normalized_weights))

    # Variance and SE
    variance = sum(((theta - theta_eap) ** 2) * w for theta, w in zip(grid, normalized_weights))
    se = math.sqrt(max(variance, 1e-6))

    theta_clamped = max(lower, min(upper, theta_eap))
    return round(theta_clamped, 4), round(se, 4)


def estimate_theta_mle(
    theta_init: float,
    responses: List[Dict[str, Any]],
    max_iter: int = 30,
    tol: float = 1e-5,
    clamp_range: Tuple[float, float] = DEFAULT_CLAMP_RANGE
) -> Tuple[float, float]:
    """Maximum Likelihood Estimation (MLE) of theta via Newton-Raphson.

    Includes step-limiting (|delta| <= 1.0) and range clamping.

    Args:
        theta_init: Initial theta estimate.
        responses: List of dicts with 'a', 'b', 'c', 'is_correct'.
        max_iter: Max Newton-Raphson iterations (default 30).
        tol: Convergence tolerance for first derivative (default 1e-5).
        clamp_range: Min and max bounds for theta (default [-4.0, 4.0]).

    Returns:
        Tuple[float, float]: (estimated_theta, standard_error).
    """
    if not responses:
        return theta_init, 999.0

    lower, upper = clamp_range
    theta = max(lower, min(upper, theta_init))

    for _ in range(max_iter):
        l1 = 0.0
        l2 = 0.0

        for r in responses:
            a = float(r["a"])
            b = float(r["b"])
            c = float(r["c"])
            u = 1.0 if r["is_correct"] else 0.0

            p = p_correct(theta, a, b, c)
            q = 1.0 - p
            denom_c = 1.0 - c
            if denom_c <= 0.0 or p * q <= 1e-12:
                continue

            p_prime = a * (p - c) * q / denom_c
            l1 += p_prime * (u - p) / (p * q)
            l2 -= (p_prime ** 2) / (p * q)

        if abs(l1) < tol or abs(l2) < 1e-12:
            break

        delta = -l1 / l2
        # Step-limiting to prevent oscillation/divergence
        delta = max(-1.0, min(1.0, delta))
        theta += delta
        theta = max(lower, min(upper, theta))

    total_info = sum(
        fisher_information(theta, float(r["a"]), float(r["b"]), float(r["c"]))
        for r in responses
    )
    # Include unit normal prior precision (1.0) so SE remains bounded and well-behaved in 3PL tail regions
    posterior_precision = 1.0 + total_info
    se = 1.0 / math.sqrt(posterior_precision) if posterior_precision > 0.0 else 1.0

    return round(theta, 4), round(se, 4)


def update_theta(
    current_theta: float,
    responses: List[Dict[str, Any]],
    clamp_range: Tuple[float, float] = DEFAULT_CLAMP_RANGE
) -> Tuple[float, float]:
    """Hybrid ability update: EAP for first 5 items or homogeneous responses, regularized MLE/EAP thereafter.

    Args:
        current_theta: Current ability estimate.
        responses: Historical response items with 'a', 'b', 'c', 'is_correct'.
        clamp_range: Clamping bounds for theta (default [-4.0, 4.0]).

    Returns:
        Tuple[float, float]: (new_theta, new_se).
    """
    if not responses:
        return current_theta, 1.0

    correct_count = sum(1 for r in responses if r["is_correct"])
    total_count = len(responses)

    eap_theta, eap_se = estimate_theta_eap(
        responses, prior_mean=0.0, prior_sd=1.0, clamp_range=clamp_range
    )

    # Use EAP if few items administered, or responses are all correct / all wrong
    if total_count <= EAP_THRESHOLD_ITEMS or correct_count == 0 or correct_count == total_count:
        return eap_theta, eap_se

    # Use MLE with EAP as robust starting point
    mle_theta, mle_se = estimate_theta_mle(eap_theta, responses, clamp_range=clamp_range)

    # If MLE diverged to boundary or has larger uncertainty than EAP, prefer EAP
    if (
        mle_se >= 1.0
        or math.isnan(mle_se)
        or math.isnan(mle_theta)
        or abs(mle_theta - eap_theta) > 1.2
    ):
        return eap_theta, min(eap_se, mle_se)

    return mle_theta, min(mle_se, eap_se)


def select_next_question(
    current_theta: float,
    candidates: List[Dict[str, Any]],
    used_question_ids: Optional[List[str]] = None
) -> Optional[Tuple[Dict[str, Any], float]]:
    """Select next question that maximizes Fisher Information I(theta).

    Deterministic tie-breaking using question ID.

    Args:
        current_theta: Student's current ability estimate.
        candidates: List of available question dicts/objects.
            Must contain 'id', 'irt_discrimination' or 'a', 'irt_difficulty' or 'b', 'irt_guessing' or 'c'.
        used_question_ids: IDs of questions already administered in this session.

    Returns:
        Optional[Tuple[Dict[str, Any], float]]: (selected_question, fisher_info_at_selection) or None if no candidates.
    """
    used_set = set(str(qid) for qid in (used_question_ids or []))

    best_item = None
    max_info = -1.0

    for item in candidates:
        item_id = str(item.get("id") if isinstance(item, dict) else getattr(item, "id"))
        if item_id in used_set:
            continue

        a = float(item.get("irt_discrimination", item.get("a", 1.0)) if isinstance(item, dict) else getattr(item, "irt_discrimination", 1.0))
        b = float(item.get("irt_difficulty", item.get("b", 0.0)) if isinstance(item, dict) else getattr(item, "irt_difficulty", 0.0))
        c = float(item.get("irt_guessing", item.get("c", 0.25)) if isinstance(item, dict) else getattr(item, "irt_guessing", 0.25))

        info = fisher_information(current_theta, a, b, c)

        if info > max_info:
            max_info = info
            best_item = item
        elif abs(info - max_info) < 1e-9:
            # Deterministic tie-breaker: smaller UUID string
            best_id = str(best_item.get("id") if isinstance(best_item, dict) else getattr(best_item, "id"))
            if item_id < best_id:
                best_item = item

    if best_item is None:
        return None

    return best_item, round(max_info, 6)


def theta_to_band(theta: float) -> float:
    """Convert latent ability theta to estimated IELTS Band according to spec.

    Mapping:
        theta < -2.5       -> 3.5
        -2.5 <= theta < -1.5 -> 4.5
        -1.5 <= theta < -0.5 -> 5.5
        -0.5 <= theta < 0.5  -> 6.5
        0.5 <= theta < 1.5   -> 7.5
        1.5 <= theta < 2.5   -> 8.5
        theta >= 2.5       -> 9.0

    Args:
        theta: Estimated ability.

    Returns:
        float: Estimated IELTS Band score (between 3.5 and 9.0).
    """
    if theta < -2.5:
        return 3.5
    elif theta < -1.5:
        return 4.5
    elif theta < -0.5:
        return 5.5
    elif theta < 0.5:
        return 6.5
    elif theta < 1.5:
        return 7.5
    elif theta < 2.5:
        return 8.5
    else:
        return 9.0


def is_stopping_condition_met(
    se_current: float,
    items_administered: int,
    max_items: int = DEFAULT_MAX_ITEMS,
    min_items: int = DEFAULT_MIN_ITEMS,
    se_threshold: float = DEFAULT_SE_THRESHOLD
) -> Tuple[bool, Optional[str]]:
    """Check if the adaptive testing session should terminate.

    Conditions:
    1. Reached max items limit: stop with 'max_items'.
    2. Reached SE threshold (SE < threshold) and items >= min_items: stop with 'se_threshold'.

    Args:
        se_current: Current standard error of theta.
        items_administered: Number of items already answered.
        max_items: Maximum items allowed (default 20).
        min_items: Minimum items required before allowing SE stopping (default 5).
        se_threshold: SE stopping threshold (default 0.30).

    Returns:
        Tuple[bool, Optional[str]]: (should_stop, stop_reason).
    """
    if items_administered >= max_items:
        return True, "max_items"

    if items_administered >= min_items and se_current < se_threshold:
        return True, "se_threshold"

    return False, None
