import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.rank import calc_adaptive_keyword_score
from config import SCORING_WEIGHTS

def test_ranking():
    test_cases = [
        {
            "title": "SEC Approves Spot Bitcoin ETF",
            "summary": "The SEC has officially approved the first spot Bitcoin ETFs, marking a historic milestone.",
            "description": "Exempt Category + Core Entity (Full Score)"
        },
        {
            "title": "CryptoZ Project Raises $5 Million in Seed Funding",
            "summary": "A new Layer 2 project called CryptoZ has completed its Series A funding round.",
            "description": "Sensitive Category + NO Core Entity (40% Score)"
        },
        {
            "title": "Binance Labs Invests $5 Million in CryptoZ Project",
            "summary": "Binance Labs continues to expand its portfolio by investing in Layer 2 CryptoZ.",
            "description": "Sensitive Category + Core Entity (Full Score)"
        },
        {
            "title": "New Global Crypto Tax Regulation Proposed by G20",
            "summary": "Major economies agree on a unified framework for digital asset taxation.",
            "description": "Exempt Category (Market Moving) + NO Core Entity (Full Score)"
        },
        {
            "title": "Unknown DeFi Protocol Hacked for $2 Million",
            "summary": "A vulnerability in the smart contract led to a multi-million dollar theft.",
            "description": "Sensitive Category + NO Core Entity (40% Score)"
        },
        {
            "title": "XRP Ledger Exploit: Hacker Steals $20 Million",
            "summary": "The Ripple community is alerted following a major security breach on the network.",
            "description": "Sensitive Category + Core Entity (Full Score)"
        }
    ]

    kw_freqs = {} # Empty for simulation

    print("\n--- KẾT QUẢ MÔ PHỎNG CHẤM ĐIỂM V3.2 (TOKEN-DEPENDENT) ---\n")
    print(f"{'Tiêu đề':<60} | {'Điểm':<10} | {'Keywords':<40}")
    print("-" * 120)

    for case in test_cases:
        pos, neg, words, mod, priority = calc_adaptive_keyword_score(case['title'], case['summary'], kw_freqs)
        total = pos + neg
        print(f"{case['title'][:60]:<60} | {total:<10.2f} | {', '.join(words[:5])}")

if __name__ == "__main__":
    test_ranking()
