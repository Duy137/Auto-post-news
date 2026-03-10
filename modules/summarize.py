import logging
import time
from typing import List, Optional

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Article
from config import LLM_CONFIG, LLM_PROMPT_CONFIG, PROMPT_TEMPLATES

from openai import OpenAI, APIConnectionError, APIError, RateLimitError, APITimeoutError
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, RetryError, ServiceUnavailable
from google.auth.exceptions import DefaultCredentialsError

logger = logging.getLogger(__name__)
ACTIVE_PROVIDER = LLM_CONFIG.get("active_provider", "gemini")
MAX_RETRIES = LLM_CONFIG["max_retries"]

# --- SETUP OPENAI QUOTE STATE (Removed global client, using explicit keys instead) ---
# --- SETUP GEMINI QUOTE STATE (Removed global config, using explicit keys instead) ---

# Phase 2: Prompt Abstraction Layer
def get_prompt(lane: str, platform: Optional[str] = None) -> str:
    """
    Tương lai hóa: Lấy prompt dưa trên channel (RSS, EXPRESS) và platform mong muốn.
    """
    lane = lane.upper()
    
    # 1. Thử lấy theo tuple (lane, platform) nếu có trong tương lai
    if platform:
        platform = platform.lower()
        specific_key = (lane, platform)
        if specific_key in PROMPT_TEMPLATES:
            return PROMPT_TEMPLATES[specific_key]
            
    # 2. Rơi về mức cơ bản của Lane
    if lane in PROMPT_TEMPLATES:
        return PROMPT_TEMPLATES[lane]
        
    # 3. Fallback cuối cùng
    return LLM_PROMPT_CONFIG["system_prompt"]

def _get_gemini_model(system_instruction: str, model_name: str, api_key: str):
    """Tạo Gemini Model instance với instruction tùy chỉnh động tại runtime."""
    if not api_key or api_key == "dummy_key_for_test":
        return None
        
    genai.configure(api_key=api_key)
        
    if "gemma" in model_name.lower():
        # Các model Gemma hiện không hỗ trợ tham số system_instruction qua API
        return genai.GenerativeModel(model_name=model_name)
    else:
        return genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )

def generate_rewrite_prompt(article: Article) -> str:
    """Tạo tin nhắn User Prompt để nạp vào LLM từ Object Article gốc."""
    title = article.get("title", "")
    summary = article.get("summary", "")
    source = article.get("source_name", "News Source")

    prompt = f"Source: {source}\n\nTitle: {title}\n\n"
    if summary:
        # Lọc bớt HTML tags trong summary nếu feedparser bóc sót
        import re
        clean_summary = re.sub(r'<[^>]+>', '', summary)
        prompt += f"Summary: {clean_summary}\n\n"
        
    prompt += "Analyze the above and return strictly following the system rules."
    return prompt

def parse_structured_output(text: str) -> dict:
    import re
    default_res = {"headline": "", "summary": text, "impact": "", "hashtags": ""}
    
    # Regex thông minh bắt dính nội dung dù AI dùng ||| hay \n
    head_match = re.search(r"HEADLINE:\s*(.*?)(?=\s*(?:\|\|\||\n+)?\s*SUMMARY:)", text, re.IGNORECASE | re.DOTALL)
    sum_match = re.search(r"SUMMARY:\s*(.*?)(?=\s*(?:\|\|\||\n+)?\s*(?:IMPACT|HASHTAGS):)", text, re.IGNORECASE | re.DOTALL)
    impact_match = re.search(r"IMPACT:\s*(.*?)(?=\s*(?:\|\|\||\n+)?\s*(?:HASHTAGS:|$))", text, re.IGNORECASE | re.DOTALL)
    hash_match = re.search(r"HASHTAGS:\s*(.*)", text, re.IGNORECASE | re.DOTALL)
    
    if head_match and sum_match:
        return {
            "headline": head_match.group(1).strip().strip("*").strip('"'),
            "summary": sum_match.group(1).strip(),
            "impact": impact_match.group(1).strip() if impact_match else "",
            "hashtags": hash_match.group(1).strip() if hash_match else ""
        }
        
    # Fallback 1 cho cơ chế cũ nếu regex có label trượt
    parts = [p.strip() for p in text.split("|||")]
    if len(parts) >= 3:
        headline, summary, impact, hashtags = "", "", "", ""
        for p in parts:
            if re.match(r"^HEADLINE:", p, re.IGNORECASE):
                headline = re.sub(r"^HEADLINE:\s*", "", p, flags=re.IGNORECASE).strip().strip("*").strip('"')
            elif re.match(r"^SUMMARY:", p, re.IGNORECASE):
                summary = re.sub(r"^SUMMARY:\s*", "", p, flags=re.IGNORECASE).strip()
            elif re.match(r"^IMPACT:", p, re.IGNORECASE):
                impact = re.sub(r"^IMPACT:\s*", "", p, flags=re.IGNORECASE).strip()
            elif re.match(r"^HASHTAGS:", p, re.IGNORECASE):
                hashtags = re.sub(r"^HASHTAGS:\s*", "", p, flags=re.IGNORECASE).strip()
                
        # Nếu cắt bừa không thấy nhãn, lấy theo thứ tự
        if not headline and not summary:
            headline = parts[0].replace("HEADLINE:", "").strip().strip("*").strip('"')
            summary = parts[1].replace("SUMMARY:", "").strip()
            if len(parts) > 2:
                if "HASHTAGS" in parts[2].upper():
                    hashtags = parts[2].replace("HASHTAGS:", "").strip()
                else:
                    impact = parts[2].replace("IMPACT:", "").strip()
            if len(parts) > 3:
                hashtags = parts[3].replace("HASHTAGS:", "").strip()
                
        return {
            "headline": headline,
            "summary": summary,
            "impact": impact,
            "hashtags": hashtags
        }
        
    # Fallback 2 (Ultimate): Đề phòng trường hợp AI quên hẳn bộ nhãn (HEADLINE, SUMMARY)
    # Nó chỉ trả về text thô (có thể kèm dính nhãn HASHTAGS hoặc không).
    cleaned_summary = text
    hashtags = ""
    impact = ""
    headline = ""
    
    # 1. Trích xuất HASHTAGS
    hash_match2 = re.search(r"(?:\|\|\||\n)?\s*HASHTAGS:\s*(.*)", cleaned_summary, re.IGNORECASE | re.DOTALL)
    if hash_match2:
        hashtags = hash_match2.group(1).strip()
        cleaned_summary = cleaned_summary[:hash_match2.start()].strip()
        
    # 1.5 Trích xuất IMPACT
    imp_match2 = re.search(r"(?:\|\|\||\n)?\s*IMPACT:\s*(.*)", cleaned_summary, re.IGNORECASE | re.DOTALL)
    if imp_match2:
        impact = imp_match2.group(1).strip()
        cleaned_summary = cleaned_summary[:imp_match2.start()].strip()
        
    # 2. Thử tách đoạn vắn đầu tiên làm Headline
    lines = [line.strip() for line in cleaned_summary.split('\n') if line.strip()]
    if len(lines) >= 2:
        headline = lines[0].strip("*").strip('"').replace("HEADLINE:", "").strip()
        summary = "\n\n".join(lines[1:]).replace("SUMMARY:", "").strip()
    else:
        # Trường hợp xấu nhất hệ thống không thể bóc tách (Tránh bị empty string)
        headline = "Bản tin vắn tắt"
        summary = cleaned_summary.replace("SUMMARY:", "").strip()
        
    return {
        "headline": headline,
        "summary": summary,
        "impact": impact,
        "hashtags": hashtags
    }

def _call_openai(system_prompt: str, user_prompt: str, api_key: str, model_name: str, timeout: int) -> Optional[str]:
    """Call OpenAI API."""
    if not api_key or api_key == "dummy_key_for_test":
        return None
        
    try:
        temp_client = OpenAI(api_key=api_key, timeout=timeout)
        response = temp_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=LLM_CONFIG["max_tokens"],
            temperature=LLM_CONFIG["temperature"]
        )
        return response.choices[0].message.content.strip()
    except RateLimitError:
        logger.warning(f"OpenAI Rate Limit Exceeded on model {model_name}. Marking key as exhausted.")
        return "RATE_LIMIT"
    except (APIConnectionError, APITimeoutError) as e:
        logger.warning(f"OpenAI Network/Timeout error ({timeout}s): {e}.")
        return "FATAL_ERROR"  # Break inner loop on timeout
    except APIError as e:
        logger.error(f"OpenAI API Error: {e}")
        return "FATAL_ERROR"
    except Exception as e:
        logger.error(f"Unknown Fatal Exception during OpenAI Call: {e}")
        return "FATAL_ERROR"
    return None

def _call_gemini(system_prompt: str, user_prompt: str, api_key: str, model_name: str, timeout: int) -> Optional[str]:
    """Call Google Gemini API."""
    gemini_model = _get_gemini_model(system_prompt, model_name, api_key)
    if not gemini_model:
        return None
        
    try:
        if "gemma" in model_name.lower():
            # Ghép prompt thủ công vì Gemma không hỗ trợ tham số system_instruction
            final_prompt = f"System Rules and Context:\n{system_prompt}\n\nTask:\n{user_prompt}"
        else:
            final_prompt = user_prompt

        response = gemini_model.generate_content(
            final_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=LLM_CONFIG["temperature"]
            ),
            request_options={"timeout": timeout}
        )
        return response.text.strip()
    except ResourceExhausted:
        logger.warning(f"Gemini Rate Limit Exceeded on model {model_name}. Marking key as exhausted.")
        return "RATE_LIMIT"
    except DefaultCredentialsError:
        logger.warning(f"Gemini API Key format invalid bounds.")
        return "FATAL_ERROR"
    except (RetryError, ServiceUnavailable) as e:
        logger.warning(f"Gemini Timeout/ServiceUnavailable ({timeout}s): {e}.")
        return "FATAL_ERROR" # Break on timeout
    except Exception as e:
        # Check specifically for generic timeouts often thrown by google API core without specific typing
        err_str = str(e).lower()
        if "timeout" in err_str or "deadline" in err_str:
            logger.warning(f"Gemini generic timeout ({timeout}s): {e}.")
            return "FATAL_ERROR"
            
        logger.error(f"Fatal Exception during Gemini Call: {e}")
        return "FATAL_ERROR"
    return None

def call_llm_with_retry(system_prompt: str, user_prompt: str, lane: str = "RSS") -> Optional[str]:
    """Wraps API call with Provider Router, API Key Rotation, and Model Degradation Fallback."""
    lane = lane.upper()
    provider = ACTIVE_PROVIDER
    
    api_keys = LLM_CONFIG.get(provider, {}).get("api_keys", ["dummy_key_for_test"])
    models = LLM_CONFIG.get("lane_models", {}).get(lane, [])
    timeout = LLM_CONFIG.get("lane_timeouts", {}).get(lane, 15)
    
    if not models:
        logger.error(f"No LLM models configured for lane {lane}!")
        return None

    if len(api_keys) == 1 and api_keys[0] == "dummy_key_for_test":
        logger.warning(f"No valid {provider.upper()} API Key defined. Mocking LLM Output.")
        return f"🚨 BREAKING: Mocked tweet content based on rule generation. #{provider} #Crypto"

    # Outer Loop: Model Fallback
    for m_idx, current_model in enumerate(models):
        logger.info(f"--- Establishing LLM Base: Lane={lane} | Model={current_model} | Timeout={timeout}s ---")
        
        # Inner Loop: Key Rotation
        for k_idx, current_key in enumerate(api_keys):
            logger.info(f"[LLM] lane={lane} model={current_model} key_idx={k_idx} -> Executing Call")
            
            if provider == "openai":
                result = _call_openai(system_prompt, user_prompt, current_key, current_model, timeout)
            elif provider == "gemini":
                result = _call_gemini(system_prompt, user_prompt, current_key, current_model, timeout)
            else:
                logger.error(f"Unknown LLM Provider: {provider}")
                return None
                
            if result == "RATE_LIMIT":
                logger.warning(f"[LLM] rate limit detected -> rotating key (exhausted key_idx={k_idx})")
                continue # Try next key
                
            if result == "FATAL_ERROR": # e.g Timeout or Bad Model Config -> Give up on this model early
                logger.warning(f"[LLM] fatal error/timeout -> breaking key loop, escalating to model fallback.")
                break 
                
            if result is not None:
                return result
                
        # If we reach here, ALL keys for the current model failed.
        logger.warning(f"[LLM] all keys exhausted for {current_model}.")
        
        if m_idx < len(models) - 1:
            logger.warning(f"[LLM] switching to fallback model {models[m_idx+1]}")
        else:
            logger.error(f"[LLM] ALL MODELS EXHAUSTED for lane {lane}.")

    logger.error("Failed to generate tweet after exhausting all keys and all models.")
    return None

def summarize_articles(selected_articles: List[Article], lane: str = "RSS") -> List[Article]:
    """
    Main Phase 5: Gửi từng bài được chọn cho LLM viết lại nội dung.
    """
    if not selected_articles:
        return []
        
    logger.info(f"Starting Phase 5: Summarizing {len(selected_articles)} top articles for lane {lane.upper()}.")
    
    system_prompt = get_prompt(lane=lane)
    processed_articles = []
    
    for rank, article in enumerate(selected_articles):
        logger.info(f"Generatting Tweet for Article #{rank+1} - ID: {article['id']}")
        
        user_prompt = generate_rewrite_prompt(article)
        result = call_llm_with_retry(system_prompt, user_prompt, lane=lane)
        
        if result:
            article["tweet_content"] = result
            article["structured_content"] = parse_structured_output(result)
            processed_articles.append(article)
        else:
            logger.error(f"Failed to generate summary for Article: {article['title']}. Dropping from pipeline.")
            
    logger.info(f"Phase 5 Complete: Fully prepared {len(processed_articles)} articles.")
    return processed_articles

if __name__ == "__main__":
    # --- MÔ PHỎNG DEBUG ---
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
    print("\n[MÔ PHỎNG PHASE 5: SUMMARIZER (LLM WRAPPER)]\n")
    
    # Input được duyệt đến list từ output của Selector (Phase 4)
    mock_selected = [
        {
            "id": "111", 
            "title": "US SEC officially approves 11 spot Bitcoin ETFs in historic decision", 
            "link": "link1", "raw_source_url": "", 
            "summary": "After a decade of denials, the United States Securities and Exchange Commission has approved the first spot Bitcoin exchange-traded funds. Trading is expected to begin tomorrow across major exchanges like NYSE and Nasdaq.", 
            "published_ts": 123, "source_name": "CoinTelegraph",
            "score": 25.0, "score_detail": None, "tweet_content": None
        }
    ]
    
    print("--- [DEBUG] PROMPT CONSTRUCTION ---")
    sys_p = LLM_PROMPT_CONFIG["system_prompt"]
    usr_p = generate_rewrite_prompt(mock_selected[0])
    print(f"SYSTEM PROMPT:\n{sys_p}\n")
    print(f"USER PROMPT:\n{usr_p}\n")
    
    print("--- [DEBUG] CALLING LLM MOCK ---")
    final_articles = summarize_articles(mock_selected)
    
    print("\n--- [DEBUG] FINAL OUTPUT ---")
    if final_articles:
        for a in final_articles:
            print(f"STRUCTURED CONTENT:\n{a['structured_content']}\n"
                  f"🔗 {a['link']}\n")
