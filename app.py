"""刷题助手 — Streamlit 前端
入口：streamlit run app.py
Python：g:/miniconda3/envs/exam/python
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中，以便导入 exam_app 包
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from exam_app.models.question_bank import QuestionBank

# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(
    page_title="刷题助手 · CAIP 强脑赛道",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 自定义 CSS ────────────────────────────────────────────
st.markdown("""
<style>
    /* 全局紧凑 */
    .block-container { padding-top: 2rem; padding-bottom: 1rem; }
    /* 题目正文 */
    .question-text {
        font-size: 1.1rem;
        line-height: 1.55;
        padding: 0.15rem 0 0.3rem 0;
    }
    /* 选项标签 */
    .stRadio label, .stCheckbox label {
        font-size: 1rem;
        padding: 0.15rem 0;
    }
    .stRadio div[role="radiogroup"] { gap: 0.2rem; }
    /* 按钮 */
    .stButton button { border-radius: 8px; }
    /* 分割线 */
    hr { margin: 0.4rem 0; }
    /* subheader */
    h3 { margin-bottom: 0.2rem; padding-bottom: 0; }
    /* 文本框 */
    textarea { min-height: 100px !important; }
</style>
""", unsafe_allow_html=True)


# ── 工具函数 ──────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def list_banks() -> list[dict]:
    """扫描 quiz_banks 目录，返回题库元数据列表。"""
    banks_dir = PROJECT_ROOT / "exam_app" / "quiz_banks"
    result: list[dict] = []
    for fp in sorted(banks_dir.glob("*.json")):
        try:
            bank = QuestionBank.load(fp)
            result.append({
                "id": fp.name,
                "name": bank.name,
                "description": bank.description,
                "question_count": bank.question_count,
            })
        except Exception:
            pass
    return result


@st.cache_data(show_spinner="加载题库中…")
def load_bank_data(bank_id: str) -> dict:
    """加载题库完整数据，返回可序列化的 dict。"""
    fp = PROJECT_ROOT / "exam_app" / "quiz_banks" / bank_id
    bank = QuestionBank.load(fp)
    questions: list[dict] = []
    for q in bank.questions:
        questions.append({
            "id": q.id,
            "type": q.type.value,
            "question": q.question,
            "options": q.options,
            "answer": q.answer,
            "explanation": q.explanation,
        })
    return {
        "name": bank.name,
        "description": bank.description,
        "question_count": bank.question_count,
        "questions": questions,
    }


def init_session() -> None:
    """初始化 session_state 中的持久变量。"""
    defaults = {
        "bank_id": None,          # 当前题库文件名
        "bank": None,             # 题库 dict (由 load_bank_data 返回)
        "index": 0,               # 当前题目索引
        "records": {},            # index → {user_answer, is_correct, correct_answer, explanation}
        "show_answer": set(),     # 已点"显示答案"的题目索引集合
        "submitted": set(),       # 已提交的题目索引集合
        "shuffle_maps": {},       # index → (shuffled_options, fwd_map, rev_map)
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def switch_bank(bank_id: str) -> None:
    """切换题库时重置全部状态。"""
    st.session_state.bank_id = bank_id
    st.session_state.bank = load_bank_data(bank_id)
    st.session_state.index = 0
    st.session_state.records = {}
    st.session_state.show_answer = set()
    st.session_state.submitted = set()
    st.session_state.shuffle_maps = {}


def go_to_question(idx: int, total: int) -> bool:
    """安全跳转到指定题目。"""
    if 0 <= idx < total:
        st.session_state.index = idx
        return True
    return False


# ── 选项打乱 ──────────────────────────────────────────────

def build_shuffled_options(original_options: list[str], q_index: int) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """以题目索引为种子，确定性打乱选项顺序。

    返回:
        shuffled_options: 重新标号后的选项列表，如 ["A. 文本", "B. 文本", ...]
        forward_map:     display_letter → original_letter （提交时翻译用）
        reverse_map:     original_letter → display_letter （展示答案时翻译用）
    """
    import random, re

    if len(original_options) < 2:
        # 无需打乱
        orig_letters = [chr(ord('A') + i) for i in range(len(original_options))]
        return list(original_options), {}, {}

    rng = random.Random(q_index)
    indices = list(range(len(original_options)))
    rng.shuffle(indices)

    # 去除原有字母前缀
    def strip_label(opt: str) -> str:
        m = re.match(r'^[A-Z]\.\s*', opt)
        return opt[m.end():] if m else opt

    stripped = [strip_label(o) for o in original_options]
    orig_letters = [chr(ord('A') + i) for i in range(len(original_options))]

    shuffled: list[str] = []
    forward_map: dict[str, str] = {}
    reverse_map: dict[str, str] = {}
    for new_i, old_i in enumerate(indices):
        new_letter = chr(ord('A') + new_i)
        old_letter = orig_letters[old_i]
        forward_map[new_letter] = old_letter
        reverse_map[old_letter] = new_letter
        shuffled.append(f"{new_letter}. {stripped[old_i]}")

    return shuffled, forward_map, reverse_map


# ── 判题逻辑 ──────────────────────────────────────────────

def check_single(user_letter: str, correct: str) -> bool:
    return user_letter.strip().upper() == correct.strip().upper()


def check_multiple(user_letters: list[str], correct) -> bool:
    if isinstance(correct, list):
        return sorted(user_letters) == sorted(correct)
    # 兼容字符串格式 "A,B,C"
    correct_list = [c.strip().upper() for c in str(correct).split(",")]
    return sorted(user_letters) == sorted(correct_list)


def format_answer(answer) -> str:
    """将答案转为可读字符串。"""
    if isinstance(answer, list):
        return "、".join(str(a) for a in answer)
    return str(answer) if answer else "（无）"


# ── 解析字母翻译 ──────────────────────────────────────────

def _translate_explanation(text: str, rev_map: dict[str, str]) -> str:
    """将解析文本中的原始选项字母替换为打乱后的显示字母。

    用正则匹配独立大写字母（不被英文字母包围），避免误伤英文单词。
    例如 "排除D" 在 D→B 后变为 "排除B"，但 "API" 中的 A 不受影响。
    """
    import re
    if not rev_map or not text:
        return text
    return re.sub(
        r'(?<![A-Za-z])([A-Z])(?![A-Za-z])',
        lambda m: rev_map.get(m.group(1), m.group(1)),
        text,
    )


# ── 页面渲染 ──────────────────────────────────────────────

def render_result(record_key: int, rev_map: dict[str, str] | None = None) -> None:
    """展示已提交题目的评判结果。"""
    record = st.session_state.records.get(record_key)
    if record is None:
        return
    st.markdown("<hr style='margin:0.4rem 0'>", unsafe_allow_html=True)
    is_correct = record.get("is_correct")
    if is_correct is None:
        st.info("📝 简答题已提交，请自行对照答案评判")
    elif is_correct:
        st.success("✅ 回答正确！")
    else:
        st.error("❌ 回答错误")

    correct_answer = record.get("correct_answer")
    if correct_answer:
        st.markdown(f"**正确答案：** {format_answer(correct_answer)}")
    explanation = record.get("explanation")
    if explanation and rev_map:
        explanation = _translate_explanation(explanation, rev_map)
    if explanation:
        st.markdown(f"**解析：** {explanation}")


def render_answer_peek(question: dict, rev_map: dict[str, str] | None = None) -> None:
    """显示答案预览（未提交时偷看）。"""
    st.markdown("<hr style='margin:0.4rem 0'>", unsafe_allow_html=True)
    st.info("💡 答案预览（未提交）")
    answer = question.get("answer")
    if answer:
        if question["type"] == "truefalse":
            # 判断题：T/F → 正确/错误
            answer = "正确" if str(answer).strip().upper() == "T" else "错误"
        elif rev_map:
            # 若选项已打乱，将原始答案转为显示字母并排序
            if isinstance(answer, list):
                answer = sorted(rev_map.get(a, a) for a in answer)
            else:
                answer = rev_map.get(answer, answer)
        st.markdown(f"**正确答案：** {format_answer(answer)}")
    explanation = question.get("explanation")
    if explanation and rev_map:
        explanation = _translate_explanation(explanation, rev_map)
    if explanation:
        st.markdown(f"**解析：** {explanation}")


def render_single_choice(question: dict, shuffled_opts: list[str],
                         fwd_map: dict[str, str], rev_map: dict[str, str],
                         record_key: int) -> None:
    """单选题 / 判断题：radio + 提交 + 显示答案。"""
    option_letters = [opt.strip()[0].upper() for opt in shuffled_opts]
    is_submitted = record_key in st.session_state.submitted
    answer_shown = record_key in st.session_state.show_answer

    # 恢复之前的选项
    prev = st.session_state.records.get(record_key, {})
    prev_idx = 0
    if prev.get("user_answer"):
        is_tf = (question["type"] == "truefalse")
        if is_tf:
            # 判断题：T → "正确"，F → "错误"，匹配选项文本
            target = "正确" if str(prev["user_answer"]).strip().upper() == "T" else "错误"
            for i, opt in enumerate(shuffled_opts):
                if target in opt:
                    prev_idx = i
                    break
        elif rev_map:
            prev_display = rev_map.get(prev["user_answer"], prev["user_answer"])
            for i, letter in enumerate(option_letters):
                if letter.upper() == prev_display.strip().upper():
                    prev_idx = i
                    break
        else:
            for i, letter in enumerate(option_letters):
                if letter.upper() == str(prev["user_answer"]).strip().upper():
                    prev_idx = i
                    break

    selected_idx = st.radio(
        "请选择一个答案：",
        options=range(len(shuffled_opts)),
        format_func=lambda i: shuffled_opts[i],
        index=prev_idx,
        key=f"radio_{record_key}",
        disabled=is_submitted,
        label_visibility="collapsed",
    )

    c_left, c_right = st.columns([1, 2])
    with c_left:
        if answer_shown:
            if st.button("🙈 隐藏答案", key=f"hide_{record_key}", use_container_width=True):
                st.session_state.show_answer.discard(record_key)
                st.rerun()
        else:
            if st.button("💡 显示答案", key=f"show_{record_key}",
                         disabled=is_submitted, use_container_width=True):
                st.session_state.show_answer.add(record_key)
                st.rerun()

    with c_right:
        if st.button("📤 提交答案", key=f"sub_{record_key}",
                     disabled=is_submitted, use_container_width=True):
            is_tf = (question["type"] == "truefalse")
            selected_text = shuffled_opts[selected_idx]

            if is_tf:
                # 判断题：根据选项文本中是否含"正确/对"映射到 T/F
                original_answer = "T" if ("正确" in selected_text or "对" in selected_text) else "F"
                correct_display = "正确" if question["answer"].strip().upper() == "T" else "错误"
            else:
                # 单选题：显示字母 → 原始字母
                display_answer = option_letters[selected_idx]
                original_answer = fwd_map.get(display_answer, display_answer) if fwd_map else display_answer
                correct_original_letter = question["answer"]
                correct_display = rev_map.get(correct_original_letter, correct_original_letter) if rev_map else correct_original_letter

            is_correct = check_single(original_answer, question["answer"])
            st.session_state.records[record_key] = {
                "user_answer": original_answer,
                "is_correct": is_correct,
                "correct_answer": correct_display,
                "explanation": question.get("explanation", ""),
            }
            st.session_state.submitted.add(record_key)
            st.rerun()


def render_multiple_choice(question: dict, shuffled_opts: list[str],
                           fwd_map: dict[str, str], rev_map: dict[str, str],
                           record_key: int) -> None:
    """多选题：checkboxes + 提交按钮 + 显示答案。"""
    option_letters = [opt.strip()[0].upper() for opt in shuffled_opts]
    is_submitted = record_key in st.session_state.submitted
    answer_shown = record_key in st.session_state.show_answer

    # 恢复之前的勾选（记录中存的是原始字母，需转回显示字母）
    prev = st.session_state.records.get(record_key, {})
    prev_set: set[str] = set()
    if prev.get("user_answer"):
        if rev_map:
            prev_set = {rev_map.get(a.strip().upper(), a.strip().upper()) for a in prev["user_answer"]}
        else:
            prev_set = {a.strip().upper() for a in prev["user_answer"]}

    checked: list[bool] = []
    for i, opt in enumerate(shuffled_opts):
        default = option_letters[i] in prev_set
        c = st.checkbox(
            opt,
            value=default,
            key=f"mc_{record_key}_{i}",
            disabled=is_submitted,
        )
        checked.append(c)

    c_left, c_right = st.columns([1, 2])
    with c_left:
        if answer_shown:
            if st.button("🙈 隐藏答案", key=f"hide_{record_key}", use_container_width=True):
                st.session_state.show_answer.discard(record_key)
                st.rerun()
        else:
            if st.button("💡 显示答案", key=f"show_{record_key}",
                         disabled=is_submitted, use_container_width=True):
                st.session_state.show_answer.add(record_key)
                st.rerun()

    with c_right:
        if st.button("📤 提交答案", key=f"sub_{record_key}",
                     disabled=is_submitted, use_container_width=True):
            selected_display = [option_letters[i] for i, c in enumerate(checked) if c]
            if not selected_display:
                st.warning("⚠️ 请至少选择一个选项再提交")
                return
            # 翻译为原始字母再判题
            original_selected = [fwd_map.get(a, a) for a in selected_display] if fwd_map else selected_display
            correct_original = question["answer"]
            is_correct = check_multiple(original_selected, correct_original)
            # 正确答案转为显示字母（排序）
            if rev_map:
                if isinstance(correct_original, list):
                    correct_display = sorted(rev_map.get(a, a) for a in correct_original)
                else:
                    correct_display = sorted(rev_map.get(c.strip().upper(), c.strip().upper()) for c in str(correct_original).split(","))
            else:
                correct_display = correct_original
            st.session_state.records[record_key] = {
                "user_answer": original_selected,        # 存原始字母（规范化）
                "is_correct": is_correct,
                "correct_answer": correct_display,       # 显示字母
                "explanation": question.get("explanation", ""),
            }
            st.session_state.submitted.add(record_key)
            st.rerun()


def render_short_answer(question: dict, record_key: int) -> None:
    """简答题：文本框 + 提交按钮 + 显示答案。"""
    is_submitted = record_key in st.session_state.submitted
    answer_shown = record_key in st.session_state.show_answer

    prev = st.session_state.records.get(record_key, {})
    prev_text = prev.get("user_answer", "")

    user_text = st.text_area(
        "请输入你的回答：",
        value=prev_text,
        height=180,
        key=f"sa_{record_key}",
        disabled=is_submitted,
        placeholder="在此输入你的回答…",
    )

    c_left, c_right = st.columns([1, 2])
    with c_left:
        if answer_shown:
            if st.button("🙈 隐藏答案", key=f"hide_{record_key}", use_container_width=True):
                st.session_state.show_answer.discard(record_key)
                st.rerun()
        else:
            if st.button("💡 显示答案", key=f"show_{record_key}",
                         disabled=is_submitted, use_container_width=True):
                st.session_state.show_answer.add(record_key)
                st.rerun()

    with c_right:
        if st.button("📤 提交回答", key=f"sub_{record_key}",
                     disabled=is_submitted, use_container_width=True):
            if not user_text.strip():
                st.warning("⚠️ 请输入回答内容再提交")
                return
            st.session_state.records[record_key] = {
                "user_answer": user_text.strip(),
                "is_correct": None,
                "correct_answer": question.get("answer", ""),
                "explanation": question.get("explanation", ""),
            }
            st.session_state.submitted.add(record_key)
            st.rerun()


# ── 主程序 ────────────────────────────────────────────────

def main() -> None:
    init_session()
    banks = list_banks()

    # ═══ 侧边栏 ═══
    with st.sidebar:
        st.title("🧠 刷题助手")
        st.caption("2026 睿抗 · CAIP 强脑赛道")
        st.caption("大模型及智能体应用")

        if not banks:
            st.warning("未找到题库\n请将 `.json` 放入 `exam_app/quiz_banks/`")
            st.stop()

        # ── 题库选择 ──
        bank_opts = {b["id"]: f"{b['name']}（{b['question_count']}题）" for b in banks}
        selected_id = st.selectbox(
            "选择题库",
            options=list(bank_opts.keys()),
            format_func=lambda x: bank_opts[x],
            key="sidebar_bank_select",
            on_change=None,  # 由下方逻辑处理
        )

        # 切换题库检测
        if st.session_state.bank_id != selected_id:
            switch_bank(selected_id)
            st.rerun()

        bank = st.session_state.bank
        if bank is None:
            switch_bank(selected_id)
            st.rerun()

        total = bank["question_count"]

        st.divider()

        # ── 统计 ──
        answered_count = len(st.session_state.submitted)
        correct_count = sum(
            1 for i in st.session_state.submitted
            if st.session_state.records.get(i, {}).get("is_correct") is True
        )

        col_a, col_b = st.columns(2)
        col_a.metric("📋 总题数", total)
        col_b.metric("✅ 已答", answered_count)
        col_c, col_d = st.columns(2)
        col_c.metric("🎯 答对", correct_count)
        rate = f"{correct_count / answered_count * 100:.1f}%" if answered_count > 0 else "—"
        col_d.metric("📊 正确率", rate)

        st.divider()

        # ── 题目跳转 ──
        st.caption("跳转到指定题目")
        jump_col1, jump_col2 = st.columns([2, 1])
        with jump_col1:
            jump_to = st.number_input(
                "题号",
                min_value=1,
                max_value=total,
                value=st.session_state.index + 1,
                step=1,
                label_visibility="collapsed",
            )
        with jump_col2:
            if st.button("🎯 跳转", use_container_width=True):
                go_to_question(jump_to - 1, total)
                st.rerun()

    # ═══ 主区域 ═══
    if bank is None:
        st.info("请从侧边栏选择题库开始刷题")
        st.stop()

    questions = bank["questions"]
    idx = st.session_state.index

    # 边界保护
    if idx < 0 or idx >= total:
        st.session_state.index = 0
        st.rerun()

    question = questions[idx]
    record_key = idx  # 使用题库内索引用作 key

    # ── 题目头部（一行：题号类型 + 进度条）──
    type_labels = {
        "single": "单选题",
        "multiple": "多选题（不定项）",
        "truefalse": "判断题",
        "shortanswer": "简答题",
    }
    qtype = question["type"]
    h_left, h_right = st.columns([3, 2])
    with h_left:
        st.subheader(f"第 {question['id']} 题 · {type_labels.get(qtype, qtype)}")
    with h_right:
        st.progress(
            (idx + 1) / total,
            text=f"{idx + 1} / {total}",
        )

    # ── 题目正文 ──
    st.markdown(
        f"<div class='question-text'>{question['question']}</div>",
        unsafe_allow_html=True,
    )

    # ── 选项打乱（单选/多选打乱，判断题保持原序）──
    if qtype == "truefalse":
        # 判断题不打乱，只补字母前缀 "A. 正确" "B. 错误"
        if record_key not in st.session_state.shuffle_maps:
            opts = question["options"]
            shuffled_opts = [f"{chr(ord('A') + i)}. {opts[i]}" for i in range(len(opts))]
            st.session_state.shuffle_maps[record_key] = (shuffled_opts, {}, {})
    elif qtype in ("single", "multiple"):
        if record_key not in st.session_state.shuffle_maps:
            shuffled_opts, fwd_map, rev_map = build_shuffled_options(
                question["options"], record_key
            )
            st.session_state.shuffle_maps[record_key] = (shuffled_opts, fwd_map, rev_map)
    if qtype in ("single", "truefalse", "multiple"):
        shuffled_opts, fwd_map, rev_map = st.session_state.shuffle_maps[record_key]
    else:
        shuffled_opts, fwd_map, rev_map = question["options"], {}, {}

    # ── 按题型渲染 ──
    if qtype in ("single", "truefalse"):
        render_single_choice(question, shuffled_opts, fwd_map, rev_map, record_key)
    elif qtype == "multiple":
        render_multiple_choice(question, shuffled_opts, fwd_map, rev_map, record_key)
    elif qtype == "shortanswer":
        render_short_answer(question, record_key)

    # ── 底部导航 ──
    st.markdown("<hr style='margin:0.6rem 0 0.3rem 0'>", unsafe_allow_html=True)
    nav_prev, nav_status, nav_next = st.columns([1, 2, 1])

    with nav_prev:
        if st.button("⬅️ 上一题", key="nav_prev",
                     disabled=(idx <= 0), use_container_width=True):
            go_to_question(idx - 1, total)
            st.rerun()

    with nav_status:
        # 快捷导航：显示题目编号列表
        st.caption(
            f"当前：第 {idx + 1} / {total} 题　｜　"
            f"已答 {answered_count} 题　｜　"
            f"答对 {correct_count} 题"
        )

    with nav_next:
        if st.button("下一题 ➡️", key="nav_next",
                     disabled=(idx >= total - 1), use_container_width=True):
            go_to_question(idx + 1, total)
            st.rerun()

    # ── 结果 / 答案展示（导航下方，不挤占按钮位置）──
    is_submitted = record_key in st.session_state.submitted
    answer_shown = record_key in st.session_state.show_answer
    if is_submitted:
        render_result(record_key, rev_map if qtype != "shortanswer" else None)
    elif answer_shown:
        render_answer_peek(question, rev_map if qtype != "shortanswer" else None)


if __name__ == "__main__":
    main()
