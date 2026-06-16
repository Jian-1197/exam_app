"""题库数据模型 —— 纯 Python，无 Qt 依赖"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import json


class QuestionType(Enum):
    SINGLE = "single"           # 单选题
    MULTIPLE = "multiple"       # 多选题（不定项）
    TRUEFALSE = "truefalse"     # 判断题
    SHORTANSWER = "shortanswer" # 简答题


@dataclass
class Question:
    """单道题目"""
    id: int
    type: QuestionType
    question: str
    options: list[str] = field(default_factory=list)
    answer: Optional[str | list[str]] = None  # single/truefalse→str, multiple→list[str], shortanswer→None
    explanation: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Question":
        qtype = QuestionType(data.get("type", "single"))
        return cls(
            id=data.get("id", 0),
            type=qtype,
            question=data.get("question", ""),
            options=data.get("options", []),
            answer=data.get("answer"),
            explanation=data.get("explanation", ""),
        )

    def check_answer(self, user_answer: str | list[str]) -> bool:
        """判题：用户答案与正确答案比对"""
        if self.type == QuestionType.SHORTANSWER:
            return False  # 简答题不判
        if self.type == QuestionType.MULTIPLE:
            if not isinstance(self.answer, list) or not isinstance(user_answer, list):
                return False
            return sorted(self.answer) == sorted(user_answer)
        # single / truefalse
        if isinstance(self.answer, str) and isinstance(user_answer, str):
            return self.answer.strip().upper() == user_answer.strip().upper()
        return False


class QuestionBank:
    """题库：加载 JSON 文件，管理题目集合"""

    def __init__(self) -> None:
        self.name: str = ""
        self.description: str = ""
        self.questions: list[Question] = []
        self._path: Optional[Path] = None

    @property
    def question_count(self) -> int:
        return len(self.questions)

    @classmethod
    def load(cls, path: str | Path) -> "QuestionBank":
        """从 JSON 文件加载题库"""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        bank = cls()
        bank._path = path
        bank.name = data.get("name", path.stem)
        bank.description = data.get("description", "")
        bank.questions = [
            Question.from_dict(q) for q in data.get("questions", [])
        ]
        # 若 JSON 未提供 id，按顺序赋值
        for i, q in enumerate(bank.questions):
            if q.id == 0:
                q.id = i + 1
        return bank

    def get_question(self, index: int) -> Optional[Question]:
        if 0 <= index < len(self.questions):
            return self.questions[index]
        return None
