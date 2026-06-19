# 刷题助手 🧠

基于 Streamlit 的智能刷题工具，支持多种题型，本地 JSON 题库驱动，轻量无数据库。

## 功能

- **四种题型**：单选题、多选题（不定项）、判断题、简答题
- **错题标记**：自动记录错题，支持错题重刷
- **随机选题**：可自定义每次练习的题目数量
- **解析查看**：每题作答后可查看详细解析
- **美观界面**：简洁响应式布局，支持亮色/暗色主题

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
```

打开浏览器访问 `http://localhost:8501` 即可使用。

## 题库格式

题库为 JSON 文件，存放在 `exam_app/quiz_banks/` 目录下。单题结构：

```json
{
  "id": 1,
  "type": "single",
  "question": "题目内容",
  "options": ["A. 选项1", "B. 选项2", "C. 选项3", "D. 选项4"],
  "answer": "A",
  "explanation": "答案解析"
}
```

### 题型枚举

| 类型 | `type` 值 | `answer` 格式 |
|------|-----------|---------------|
| 单选题 | `single` | `"A"` |
| 多选题 | `multiple` | `["A", "C"]` |
| 判断题 | `truefalse` | `"对"` / `"错"` |
| 简答题 | `shortanswer` | 无 |

## 项目结构

```
exam_app/
├── app.py                      # Streamlit 入口
├── requirements.txt            # 依赖
├── exam_app/
│   ├── models/
│   │   └── question_bank.py    # 数据模型（Question, QuestionBank）
│   └── quiz_banks/
│       ├── 样题1.json          # 样题库1
│       └── 样题2.json          # 样题库2
└── README.md
```
