import math
from datetime import datetime, timedelta
from app.models.flashcard import Rating, ReviewState

# FSRS v4 default pre-trained weights (w0-w16 are operative, w17-w19 reserved)
# Source: open-spaced-repetition/fsrs4anki — commonly adopted defaults
DEFAULT_WEIGHTS = [
    0.5701, 1.4436, 4.1386, 10.9355,   # w0-w3: initial stability (Again/Hard/Good/Easy)
    5.1846, 1.0651, 0.8624, 0.0589,     # w4-w7: difficulty & mean-reversion
    1.5330, 0.1544, 1.0040, 1.9395,     # w8-w11: SRS recall stability factors
    0.1100, 0.2900, 2.2700,             # w12-w14: forget-path factors
    0.2900, 2.6100, 0.0, 0.0, 0.0      # w15-w19
]

# FSRS target retrievability (90% retention at scheduled interval)
DESIRED_RETENTION = 0.90

class FSRSEngine:
    """
    FSRS (Free Spaced Repetition Scheduler) v4 implementation.
    """
    def __init__(self, weights=None):
        if weights is None:
            weights = DEFAULT_WEIGHTS
        self.w = weights
        self.decay = -0.5
        self.factor = 19.0 / 81.0

    def calculate_next_review(self, rating: Rating, state: ReviewState, stability: float, difficulty: float, retrievability: float, lapses: int, reps: int, last_review_date: datetime, now: datetime):
        if state == ReviewState.NEW:
            stability = self._init_stability(rating)
            difficulty = self._init_difficulty(rating)
            lapses = 0
            reps = 1
            state = ReviewState.LEARNING if rating in [Rating.AGAIN, Rating.HARD] else ReviewState.REVIEW
            retrievability = 1.0
        else:
            if last_review_date:
                interval_days = max(0, (now - last_review_date).days)
                retrievability = self._forgetting_curve(interval_days, stability)
            else:
                retrievability = 1.0
            
            if rating == Rating.AGAIN:
                stability = self.update_stability_after_forget(stability, difficulty, retrievability)
                difficulty = self._next_difficulty(difficulty, rating)
                state = ReviewState.RELEARNING
                lapses += 1
            else:
                stability = self.update_stability_after_recall(stability, difficulty, retrievability, rating)
                difficulty = self._next_difficulty(difficulty, rating)
                state = ReviewState.REVIEW
            reps += 1

        next_interval_days = self.next_interval(stability)
        due_date = now + timedelta(days=next_interval_days)
        
        return state, stability, difficulty, retrievability, lapses, reps, due_date

    def _init_stability(self, rating: Rating) -> float:
        mapping = {
            Rating.AGAIN: self.w[0],
            Rating.HARD: self.w[1],
            Rating.GOOD: self.w[2],
            Rating.EASY: self.w[3],
        }
        return mapping.get(rating, self.w[2])

    def _init_difficulty(self, rating: Rating) -> float:
        r_val = self._rating_to_int(rating)
        d = self.w[4] - self.w[5] * (r_val - 3)
        return min(max(d, 1.0), 10.0)

    def _next_difficulty(self, d: float, rating: Rating) -> float:
        r_val = self._rating_to_int(rating)
        next_d = d - self.w[6] * (r_val - 3)
        next_d = min(max(next_d, 1.0), 10.0)
        return self._mean_reversion(self.w[4], next_d)

    def _mean_reversion(self, init_d: float, current_d: float) -> float:
        return self.w[7] * init_d + (1 - self.w[7]) * current_d

    def _forgetting_curve(self, elapsed_days: float, stability: float) -> float:
        if stability == 0:
            return 0.0
        return math.pow(1 + self.factor * elapsed_days / stability, self.decay)

    def next_interval(self, stability: float) -> int:
        """
        Tính interval theo công thức FSRS chuẩn để đạt DESIRED_RETENTION (90%).
        I = S * (R_d^(1/decay) - 1) / factor
        Với R_d=0.9, decay=-0.5, factor=19/81:
            multiplier ≈ (0.9^(-2) - 1) / (19/81) = 0.2346 / 0.2346 ≈ 9 / 19 * 81 ...
        Thực ra FSRS simplified: I = S * multiplier where multiplier ≈ 9/19 * 81^... 
        Công thức đơn giản và chính xác nhất theo FSRS spec:
            interval = round(S * factor_r)
        trong đó factor_r = (R_d^(1/decay) - 1) / factor
        """
        r_d = DESIRED_RETENTION
        # R(t) = (1 + factor * t / S)^decay  =>  t = S * (R_d^(1/decay) - 1) / factor
        factor_r = (math.pow(r_d, 1.0 / self.decay) - 1.0) / self.factor
        interval = round(stability * factor_r)
        return max(1, interval)

    def update_stability_after_recall(self, s: float, d: float, r: float, rating: Rating) -> float:
        hard_penalty = self.w[15] if rating == Rating.HARD else 1.0
        easy_bonus = self.w[16] if rating == Rating.EASY else 1.0
        
        factor1 = math.exp(self.w[8])
        factor2 = 11.0 - d
        factor3 = math.pow(s, -self.w[9])
        factor4 = math.exp((1.0 - r) * self.w[10]) - 1.0
        
        s_new = s * (1.0 + factor1 * factor2 * factor3 * factor4 * hard_penalty * easy_bonus)
        return s_new

    def update_stability_after_forget(self, s: float, d: float, r: float) -> float:
        factor1 = math.pow(d, -self.w[12])
        factor2 = math.pow(s + 1.0, self.w[13]) - 1.0
        factor3 = math.exp((1.0 - r) * self.w[14])
        
        s_new = self.w[11] * factor1 * factor2 * factor3
        return min(s_new, s)

    def _rating_to_int(self, rating: Rating) -> int:
        if rating == Rating.AGAIN: return 1
        if rating == Rating.HARD: return 2
        if rating == Rating.GOOD: return 3
        if rating == Rating.EASY: return 4
        return 3
