"""
Mock LLM — shared utility for all lab examples.
No API key required.  Returns canned responses to focus on deployment concepts.
"""
import time
import random


MOCK_RESPONSES = {
    "default": [
        "Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.",
        "Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.",
        "Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.",
    ],
    "docker": ["Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"],
    "deploy": ["Deployment là quá trình đưa code từ máy bạn lên server để người khác dùng được."],
    "health": ["Agent đang hoạt động bình thường. All systems operational."],
    "redis": ["Redis là in-memory data store — dùng để lưu session, rate-limit counters, và cache."],
    "scale": ["Stateless design + Redis = scale horizontally with ease!"],
    "security": ["API keys, rate limiting, and cost guards keep your agent safe in production."],
}


def ask(question: str, delay: float = 0.1) -> str:
    """Mock LLM call with simulated latency."""
    time.sleep(delay + random.uniform(0, 0.05))  # simulate API latency

    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)

    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    """Mock streaming response — yields one word at a time."""
    response = ask(question)
    for word in response.split():
        time.sleep(0.05)
        yield word + " "
