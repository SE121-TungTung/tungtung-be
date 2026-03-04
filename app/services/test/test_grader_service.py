from typing import Any, List
from app.models.test import QuestionType

class BaseGrader:
    """Lớp cơ sở cho tất cả bộ chấm điểm"""
    def check(self, user_answer: Any, correct_answer: str) -> bool:
        if not correct_answer or user_answer is None:
            return False
        return self._run_logic(user_answer, str(correct_answer).strip().lower())

    def _run_logic(self, user_answer: Any, correct_norm: str) -> bool:
        raise NotImplementedError

class MultipleChoiceGrader(BaseGrader):
    def _run_logic(self, user_answer: Any, correct_norm: str) -> bool:
        if isinstance(user_answer, list):
            correct_list = {ans.strip().lower() for ans in correct_norm.split(",")}
            user_list = {str(ans).strip().lower() for ans in user_answer}
            return user_list == correct_list
        return str(user_answer).strip().lower() == correct_norm

class BooleanGrader(BaseGrader):
    """Xử lý True/False/Not Given và Yes/No/Not Given"""
    MAP = {
        "t": "true", "f": "false", "ng": "not given",
        "y": "yes", "n": "no"
    }
    def _run_logic(self, user_answer: Any, correct_norm: str) -> bool:
        user_norm = str(user_answer).strip().lower()
        user_mapped = self.MAP.get(user_norm, user_norm)
        correct_mapped = self.MAP.get(correct_norm, correct_norm)
        return user_mapped == correct_mapped

class CompletionGrader(BaseGrader):
    """Xử lý Short Answer và các loại điền từ (có nhiều đáp án chấp nhận được)"""
    def _run_logic(self, user_answer: Any, correct_norm: str) -> bool:
        user_norm = str(user_answer).strip().lower()
        # Tách các đáp án chấp nhận được qua dấu | hoặc /
        delimiters = ["|", "/"]
        acceptable_answers = [correct_norm]
        
        for delim in delimiters:
            if delim in correct_norm:
                acceptable_answers = [ans.strip() for ans in correct_norm.split(delim)]
                break
        return user_norm in acceptable_answers

class ExactMatchGrader(BaseGrader):
    """Mặc định: So khớp chính xác sau khi đã normalize"""
    def _run_logic(self, user_answer: Any, correct_norm: str) -> bool:
        return str(user_answer).strip().lower() == correct_norm
    
mcq_grader = MultipleChoiceGrader()
bool_grader = BooleanGrader()
completion_grader = CompletionGrader()
exact_grader = ExactMatchGrader()

GRADER_MAPPING = {
    QuestionType.MULTIPLE_CHOICE: mcq_grader,
    
    QuestionType.TRUE_FALSE_NOT_GIVEN: bool_grader,
    QuestionType.YES_NO_NOT_GIVEN: bool_grader,
    
    QuestionType.SHORT_ANSWER: completion_grader,
    QuestionType.SENTENCE_COMPLETION: completion_grader,
    QuestionType.SUMMARY_COMPLETION: completion_grader,
    QuestionType.NOTE_COMPLETION: completion_grader,
    QuestionType.DIAGRAM_LABELING: completion_grader,
    
    QuestionType.MATCHING_HEADINGS: exact_grader,
    QuestionType.MATCHING_INFORMATION: exact_grader,
    QuestionType.MATCHING_FEATURES: exact_grader,
}

def get_grader(q_type: QuestionType):
    return GRADER_MAPPING.get(q_type, exact_grader)

