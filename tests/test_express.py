import pytest
from modules.express.filter import score_express_message, EXPRESS_SCORE_THRESHOLD
from modules.express.fingerprint import extract_fingerprints, generate_fingerprint_signature


class TestExpressFilter:
    """Kiểm thử bộ lọc nhanh (Rule-based Express Filter)."""

    def test_core_crypto_event_passes(self):
        """Tin hack/exploit hoặc bankrupt có trọng số cốt lõi cao, phải pass ngay."""
        msg = "Tin nóng: Sàn giao dịch vừa bị hack và rút ruột 50M USD!"
        passed, score, matches = score_express_message(msg)
        assert passed is True
        assert score >= EXPRESS_SCORE_THRESHOLD
        assert any(k in matches for k in ["bị hack", "hack(ed)?", "rút ruột"])

    def test_macro_entity_synergy_bonus(self):
        """Tin kết hợp giữa Vĩ mô (lãi suất) và Định chế/Entity (Fed, Mỹ) được cộng Synergy Bonus."""
        msg = "Chủ tịch Fed phát biểu về lãi suất và lạm phát tại Mỹ"
        passed, score, matches = score_express_message(msg)
        assert passed is True
        assert "SYNERGY_BONUS (Macro+Entity)" in matches
        assert score >= 70.0  # Macro (20) + Entities + Synergy (50)

    def test_spam_giveaway_penalized(self):
        """Tin rác, lừa đảo, giveaway bị trừ điểm nặng và fail bộ lọc."""
        msg = "Tham gia ngay nhận quà giveaway khủng từ dự án"
        passed, score, _ = score_express_message(msg)
        assert passed is False
        assert score < 0.0

    def test_trivial_chatter_fails(self):
        """Chat thông thường không có từ khóa tài chính/crypto sẽ bị loại bỏ."""
        msg = "Chào buổi sáng anh em, chúc một ngày giao dịch may mắn nhé"
        passed, score, _ = score_express_message(msg)
        assert passed is False
        assert score < EXPRESS_SCORE_THRESHOLD


class TestExpressFingerprint:
    """Kiểm thử trích xuất thực thể (Named Entity / Fingerprint) cho tin vắn."""

    def test_extract_tokens_and_caps(self):
        """Trích xuất ký hiệu $TOKEN và từ viết hoa ALL CAPS."""
        text = "Breaking: $SOL and $BTC approved by SEC for new ETF"
        fps = extract_fingerprints(text)
        assert "sol" in fps
        assert "btc" in fps
        assert "sec" in fps
        assert "etf" in fps

    def test_extract_named_entities_and_titlecase(self):
        """Trích xuất tên riêng và các thực thể tĩnh."""
        text = "Donald Trump and Elon Musk discussed Bitcoin regulation"
        fps = extract_fingerprints(text)
        assert "trump" in fps or "donald trump" in fps
        assert "elon musk" in fps
        assert "bitcoin" in fps

    def test_deterministic_signature(self):
        """Chữ ký fingerprint phải có tính đơn nhất và deterministic."""
        fps = ["btc", "etf", "sec"]
        sig = generate_fingerprint_signature(fps)
        assert sig == "btc||etf||sec"
