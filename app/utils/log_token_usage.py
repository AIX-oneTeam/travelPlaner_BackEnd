def log_token_usage(logger, result, crew_name="crew"):
    """
    토큰 사용 정보를 로깅하는 함수
    
    Args:
        logger: 로깅 객체
        result: 결과 객체 (token_usage 정보 포함)
        crew_name: crew의 이름 (기본값: "crew")
    """
    try:
        token_usage = result["token_usage"]
        
        usage_info = {
            "total_tokens": token_usage.get("total_tokens", 0),
            "prompt_tokens": token_usage.get("prompt_tokens", 0),
            "cached_prompt_tokens": token_usage.get("cached_prompt_tokens", 0),
            "completion_tokens": token_usage.get("completion_tokens", 0),
            "successful_requests": token_usage.get("successful_requests", 0)
        }
        
        log_message = f"\n{crew_name} Token Usage Details:"
        for key, value in usage_info.items():
            log_message += f"\n{key}: {value}"
            
        logger.info(log_message)
        
    except AttributeError:
        logger.error(f"{crew_name}: token_usage 정보를 찾을 수 없습니다.")
    except Exception as e:
        logger.error(f"{crew_name}: 토큰 사용 정보 로깅 중 오류 발생: {str(e)}")