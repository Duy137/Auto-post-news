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
    """
    Bóc tách output từ LLM. Chiến thuật:
    1. Tìm HASHTAGS: ở cuối và bóc ra trước.
    2. Với phần còn lại, tìm HEADLINE: và SUMMARY:. 
    3. Nếu không thấy nhãn nhãn (RSS lane), dùng quy tắc xuống dòng: dòng 1 là Headline, các dòng sau là Summary.
    """
    import re
    res = {"headline": "", "summary": "", "impact": "", "hashtags": ""}
    cleaned_text = text.strip()
    
    # 1. TRÍCH XUẤT HASHTAGS (Luôn ưu tiên bóc từ dưới lên)
    # Tìm nhãn HASHTAGS: ở cuối bài
    label_hash_pattern = r"(?:\|\|\||\n+)?\s*HASHTAGS:\s*(.*)"
    label_hash_match = re.search(label_hash_pattern, cleaned_text, re.IGNORECASE | re.DOTALL)
    
    if label_hash_match:
        res["hashtags"] = label_hash_match.group(1).strip()
        cleaned_text = cleaned_text[:label_hash_match.start()].strip()
    else:
        # Cơ chế AGGRESSIVE: Tìm cụm hashtags tự do ở cuối (ví dụ: "#Bitcoin #Crypto")
        # Tìm từ cuối lên, lấy các dòng chỉ chứa hashtags
        lines = cleaned_text.split("\n")
        hashtag_lines = []
        content_lines = []
        
        # Duyệt từ dưới lên
        in_hashtag_block = True
        for line in reversed(lines):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            # Nếu dòng bắt đầu bằng # và có vẻ là 1 list hashtags
            if in_hashtag_block and all(word.startswith("#") for word in stripped_line.split()):
                hashtag_lines.insert(0, stripped_line)
            else:
                in_hashtag_block = False
                content_lines.insert(0, line)
        
        if hashtag_lines:
            res["hashtags"] = " ".join(hashtag_lines).strip()
            cleaned_text = "\n".join(content_lines).strip()
    
    # 2. TRÍCH XUẤT IMPACT (Nếu có)
    impact_pattern = r"(?:\|\|\||\n+)?\s*IMPACT:\s*(.*)"
    impact_match = re.search(impact_pattern, cleaned_text, re.IGNORECASE | re.DOTALL)
    if impact_match:
        res["impact"] = impact_match.group(1).strip()
        cleaned_text = cleaned_text[:impact_match.start()].strip()
        
    # 3. TRÍCH XUẤT HEADLINE & SUMMARY
    # Thử tìm theo nhãn trước (Dành cho Express Lane hoặc RSS đầy đủ nhãn)
    head_label_match = re.search(r"HEADLINE:\s*(.*?)(?=\s*(?:\|\|\||\n+)?\s*SUMMARY:|$)", cleaned_text, re.IGNORECASE | re.DOTALL)
    sum_label_match = re.search(r"SUMMARY:\s*(.*)", cleaned_text, re.IGNORECASE | re.DOTALL)
    
    if head_label_match and sum_label_match:
        res["headline"] = head_label_match.group(1).strip().strip("*").strip('"')
        res["summary"] = sum_label_match.group(1).strip()
    elif head_label_match:
        res["headline"] = head_label_match.group(1).strip().strip("*").strip('"')
        res["summary"] = cleaned_text[head_label_match.end():].strip()
    else:
        # Cơ chế FALLBACK: Label-Agnostic (Dành cho RSS lane chỉ có format text thô)
        # Loại bỏ nhãn HEADLINE: / SUMMARY: dính kèm nếu có để lấy text sạch
        cleaned_text = re.sub(r"^HEADLINE:\s*", "", cleaned_text, flags=re.IGNORECASE)
        lines = [l.strip() for l in cleaned_text.split("\n") if l.strip()]
        
        if len(lines) >= 2:
            res["headline"] = lines[0].strip("*").strip('"')
            # Nối các dòng còn lại, loại bỏ nhãn SUMMARY: nếu AI lỡ viết vào
            remaining_text = "\n\n".join(lines[1:])
            res["summary"] = re.sub(r"^SUMMARY:\s*", "", remaining_text, flags=re.IGNORECASE).strip()
        elif len(lines) == 1:
            res["headline"] = "Bản tin vắn"
            res["summary"] = lines[0]
        else:
            res["headline"] = "Bản tin vắn"
            res["summary"] = cleaned_text

    return res

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
