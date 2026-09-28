import pytest
import os
from modules.pipeline.summarize import (
    parse_structured_output,
    _detect_provider,
    InternalRateLimiter,
    polish_vietnamese
)

def test_parse_structured_output_standard():
    llm_output = (
        "HEADLINE: SEC CHÍNH THỨC PHÊ DUYỆT 11 QUỸ BITCOIN SPOT ETF|||"
        "SUMMARY: Sau nhiều năm chờ đợi, Ủy ban Chứng khoán Mỹ (SEC) đã thông qua các quỹ ETF giao ngay. "
        "Giao dịch dự kiến sẽ bắt đầu từ phiên ngày mai.|||"
        "IMPACT: Dòng vốn tổ chức lớn có thể chảy mạnh vào thị trường.|||"
        "HASHTAGS: #Bitcoin #ETF #SEC"
    )
    
    parsed = parse_structured_output(llm_output)
    
    assert "PHÊ DUYỆT" in parsed["headline"]
    assert "Ủy ban Chứng khoán" in parsed["summary"]
    assert "Dòng vốn" in parsed["impact"]
    assert "#Bitcoin" in parsed["hashtags"]

def test_parse_structured_output_label_agnostic_fallback():
    # Model forgets labels and just returns title line followed by bullets
    llm_output = (
        "FED GIỮ NGUYÊN LÃI SUẤT Ở MỨC 5.25%\n\n"
        "🔷 Quyết định được đưa ra sau cuộc họp FOMC kéo dài 2 ngày.\n"
        "🔷 Chủ tịch Jerome Powell phát biểu về áp lực lạm phát.\n"
        "🔷 Thị trường chứng khoán và crypto phản ứng tích cực.\n\n"
        "#Fed #FOMC #Macro"
    )
    
    parsed = parse_structured_output(llm_output)
    
    assert "FED GIỮ NGUYÊN LÃI SUẤT" in parsed["headline"]
    assert "Chủ tịch Jerome Powell" in parsed["summary"]
    assert "#Fed" in parsed["hashtags"]

def test_detect_provider():
    assert _detect_provider("gpt-4o-mini") == "openai"
    assert _detect_provider("gpt-4o") == "openai"
    assert _detect_provider("o1-preview") == "openai"
    assert _detect_provider("o3-mini") == "openai"
    
    assert _detect_provider("gemini-2.5-flash") == "gemini"
    assert _detect_provider("gemma-3-27b-it") == "gemini"

def test_internal_rate_limiter():
    limiter = InternalRateLimiter()
    model = "test-model"
    
    # Custom limits for testing
    limiter.MODEL_LIMITS[model] = {"rpd": 3, "rpm": 2}
    
    assert limiter.can_call(model) is True
    limiter.record_call(model)
    assert limiter.can_call(model) is True
    limiter.record_call(model)
    
    # Hit RPM limit (2 calls in this minute)
    assert limiter.can_call(model) is False
    assert "2/3 RPD" in limiter.get_usage(model)

def test_polish_vietnamese_disabled_by_env(monkeypatch):
    monkeypatch.setenv("POLISH_ENABLED", "False")
    
    result = polish_vietnamese("Nội dung bài viết mẫu về crypto")
    assert result is None
