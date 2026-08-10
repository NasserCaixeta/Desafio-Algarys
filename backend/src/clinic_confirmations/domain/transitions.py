def retry_delay_seconds(*, attempt: int, base: int, maximum: int) -> int:
    if attempt <= 0 or base <= 0 or maximum <= 0:
        raise ValueError("attempt, base and maximum must be positive")
    exponent = min(attempt - 1, 30)
    return min(base * (1 << exponent), maximum)
