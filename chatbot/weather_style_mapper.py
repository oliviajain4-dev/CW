def get_style_recommendation(tmp: float, reh: float, sky: int, pty: int,
                             sensitivity: int = 3) -> dict:
    sensitivity_offset = {1: -2, 2: -1, 3: 0, 4: 1, 5: 2}
    tmp_adjusted = tmp + sensitivity_offset.get(sensitivity, 0)

    if pty == 1:    precip = "rain"
    elif pty == 4:  precip = "shower"
    elif pty == 2:  precip = "sleet"
    elif pty == 3:  precip = "snow"
    else:           precip = "none"

    if tmp_adjusted <= 4:       temp_range = "freezing"
    elif tmp_adjusted <= 8:     temp_range = "very_cold"
    elif tmp_adjusted <= 11:    temp_range = "cold"
    elif tmp_adjusted <= 16:    temp_range = "cool"
    elif tmp_adjusted <= 19:    temp_range = "mild"
    elif tmp_adjusted <= 22:    temp_range = "warm"
    elif tmp_adjusted <= 27:    temp_range = "hot"
    else:                       temp_range = "very_hot"

    if reh >= 80:   humidity = "high"
    elif reh <= 40: humidity = "low"
    else:           humidity = "normal"

    mapping = {
        ("freezing", "none"):   ("영하권 맑음",
                                 ["heavy_winter", "layering"],
                                 ["패딩 (롱)", "두꺼운 울 코트", "기모 이너", "목도리", "장갑", "귀마개", "워커 부츠"],
                                 ["얇은 소재", "반팔", "캔버스 슈즈"],
                                 "체온 손실 차단이 핵심. 레이어링으로 공기층 만들기."),
        ("freezing", "snow"):   ("영하권 눈",
                                 ["heavy_winter", "waterproof", "anti_slip"],
                                 ["방수 패딩", "기모 이너", "방수 워커 부츠 (발목 이상)", "장갑", "목도리"],
                                 ["스니커즈", "얇은 소재", "스웨이드"],
                                 "체온 + 젖음 + 미끄럼 3가지 동시 차단."),
        ("freezing", "rain"):   ("영하권 비",
                                 ["heavy_winter", "waterproof"],
                                 ["방수 코트", "기모 이너", "방수 부츠", "장갑", "우산"],
                                 ["스웨이드", "캔버스"],
                                 "젖으면 체감온도 급락. 방수 최우선."),
        ("very_cold", "none"):  ("매우 추움",
                                 ["winter", "layering"],
                                 ["두꺼운 울 코트", "니트", "기모 팬츠", "목도리", "앵클 부츠"],
                                 ["얇은 재킷 단독", "반팔"],
                                 "바람 차단 + 보온. 목·손목 노출 최소화."),
        ("very_cold", "rain"):  ("매우 춥고 비",
                                 ["winter", "waterproof"],
                                 ["방수 코트", "두꺼운 니트", "방수 부츠", "우산"],
                                 ["패브릭 슈즈", "스웨이드"],
                                 "젖으면 체온 더 빠르게 내려감."),
        ("very_cold", "snow"):  ("매우 춥고 눈",
                                 ["winter", "waterproof", "anti_slip"],
                                 ["방수 코트 or 패딩", "니트", "방수 부츠 (발목 이상)", "장갑"],
                                 ["스니커즈", "스웨이드", "로퍼"],
                                 "발 젖음 + 미끄럼 방지."),
        ("cold", "none"):       ("쌀쌀함",
                                 ["autumn_winter", "layering"],
                                 ["코트 or 두꺼운 자켓", "니트 or 맨투맨", "청바지", "앵클 부츠"],
                                 ["얇은 티셔츠 단독", "샌들"],
                                 "아침저녁 온도차 대비. 탈착 쉬운 레이어 추천."),
        ("cold", "rain"):       ("쌀쌀하고 비",
                                 ["autumn_winter", "waterproof"],
                                 ["방수 자켓 or 트렌치코트", "니트", "청바지", "방수 슈즈", "우산"],
                                 ["스웨이드", "캔버스 슈즈", "흰 운동화"],
                                 "비 맞으면 체감온도 급락."),
        ("cold", "snow"):       ("쌀쌀하고 눈",
                                 ["autumn_winter", "waterproof", "anti_slip"],
                                 ["방수 자켓", "니트", "청바지", "방수 부츠"],
                                 ["로퍼", "스니커즈", "스웨이드"],
                                 "눈 녹으면 질척함. 방수 부츠로 발 보호."),
        ("cool", "none"):       ("선선함",
                                 ["autumn", "casual"],
                                 ["가디건 or 자켓", "긴팔 티셔츠", "청바지 or 슬랙스", "스니커즈"],
                                 ["패딩", "두꺼운 코트", "샌들"],
                                 "활동하기 가장 쾌적한 온도대."),
        ("cool", "rain"):       ("선선하고 비",
                                 ["autumn", "waterproof"],
                                 ["방수 자켓 or 바람막이", "긴팔", "청바지", "방수 슈즈", "우산"],
                                 ["스웨이드", "캔버스 슈즈"],
                                 "가벼운 방수 아우터면 OK."),
        ("cool", "snow"):       ("선선하고 눈",
                                 ["autumn", "waterproof"],
                                 ["방수 자켓", "긴팔", "청바지", "방수 부츠"],
                                 ["로퍼", "캔버스 슈즈"],
                                 "이 온도 눈은 금방 녹아 질척."),
        ("mild", "none"):       ("약간 쌀쌀",
                                 ["spring_autumn", "casual"],
                                 ["맨투맨 or 얇은 가디건", "면 팬츠 or 청바지", "스니커즈"],
                                 ["패딩", "두꺼운 니트"],
                                 "낮엔 쾌적, 저녁엔 살짝 쌀쌀. 얇은 겉옷 하나 챙기기."),
        ("mild", "rain"):       ("약간 쌀쌀하고 비",
                                 ["spring_autumn", "waterproof"],
                                 ["얇은 방수 자켓", "긴팔", "면 팬츠", "방수 슈즈", "우산"],
                                 ["흰 옷", "스웨이드"],
                                 "방수 자켓 하나로 해결."),
        ("warm", "none"):       ("따뜻함",
                                 ["spring_summer", "casual"],
                                 ["얇은 긴팔 or 반팔", "면 팬츠 or 청바지", "스니커즈 or 로퍼"],
                                 ["두꺼운 코트", "패딩", "기모"],
                                 "입고 벗기 쉬운 구성."),
        ("warm", "rain"):       ("따뜻하고 비",
                                 ["spring_summer", "waterproof"],
                                 ["얇은 방수 자켓", "반팔 or 얇은 긴팔", "면 팬츠", "방수 슈즈", "우산"],
                                 ["흰 옷", "스웨이드", "가죽 슈즈"],
                                 "통기성 있는 방수 소재 추천."),
        ("warm", "shower"):     ("따뜻하고 소나기",
                                 ["spring_summer", "waterproof"],
                                 ["얇은 방수 자켓", "반팔", "면 팬츠", "방수 슈즈", "접이식 우산"],
                                 ["흰 옷"],
                                 "가방에 접이식 우산 하나."),
        ("hot", "none"):        ("더움",
                                 ["summer", "light", "breathable"],
                                 ["반팔 티셔츠", "반바지 or 린넨 팬츠", "샌들 or 슬리퍼"],
                                 ["두꺼운 소재", "어두운 색상", "딱 붙는 핏"],
                                 "통기성 최우선. 밝은 색상 + 루즈핏."),
        ("hot", "rain"):        ("덥고 비",
                                 ["summer", "waterproof_light"],
                                 ["반팔", "반바지 or 방수 소재 팬츠", "방수 샌들 or 크록스", "우산"],
                                 ["흰 옷", "가죽 슈즈", "스웨이드"],
                                 "젖어도 빨리 마르는 소재."),
        ("very_hot", "none"):   ("폭염",
                                 ["summer", "ultra_light", "breathable"],
                                 ["민소매 or 반팔", "반바지 or 린넨 숏팬츠", "샌들", "모자"],
                                 ["검은 옷", "두꺼운 소재", "꽉 끼는 핏"],
                                 "열 발산 극대화. 가능한 한 얇고 밝게."),
        ("very_hot", "rain"):   ("폭염에 비",
                                 ["summer", "waterproof_light"],
                                 ["반팔", "반바지", "방수 샌들", "우산"],
                                 ["흰 옷", "가죽 슈즈"],
                                 "방수 샌들로 발만 보호."),
    }

    key = (temp_range, precip)
    if key not in mapping:
        fallback = (temp_range, "rain") if precip in ["sleet", "shower"] else (temp_range, "none")
        key = fallback if fallback in mapping else (temp_range, "none")

    condition_label, style_tags, recommended_items, avoid_items, comfort_point = mapping[key]

    humidity_note = ""
    if humidity == "high" and precip == "none":
        humidity_note = "습도가 높아요. 통기성 좋은 소재를 우선해요."
        style_tags = style_tags + ["breathable"]
    elif humidity == "low":
        humidity_note = "건조해요. 정전기 방지 소재를 고려해보세요."

    hair_shoe_acc = get_hair_shoe_acc(temp_range, precip, humidity)

    return {
        "condition_label": condition_label,
        "temp_range": temp_range,
        "precip": precip,
        "humidity_level": humidity,
        "style_tags": style_tags,
        "recommended_items": recommended_items,
        "avoid_items": avoid_items,
        "comfort_point": comfort_point,
        "humidity_note": humidity_note,
        "hair_rec": hair_shoe_acc["hair"],
        "shoe_rec": hair_shoe_acc["shoe"],
        "acc_rec":  hair_shoe_acc["acc"],
    }


def get_layering_recommendation(weather: dict, sensitivity: int = 3) -> dict:
    temp_diff = weather["temp_range_diff"]
    morning = weather["morning"]
    afternoon = weather["afternoon"]

    base = get_style_recommendation(
        morning["feels_like"], morning["reh"],
        morning["sky"], morning["pty"], sensitivity
    )

    if temp_diff < 8:
        return {
            "layering_needed": False,
            "recommendation": base
        }

    afternoon_rec = get_style_recommendation(
        afternoon["feels_like"], afternoon["reh"],
        afternoon["sky"], afternoon["pty"], sensitivity
    )

    return {
        "layering_needed": True,
        "temp_diff": temp_diff,
        "morning_tmp": morning["feels_like"],
        "afternoon_tmp": afternoon["feels_like"],
        "base_recommendation": base,
        "afternoon_recommendation": afternoon_rec,
        "layering_tip": f"일교차 {temp_diff:.0f}도예요. 아침엔 {base['condition_label']} 기준으로 입고, "
                        f"낮엔 {afternoon_rec['recommended_items'][0]} 정도로 조절하세요."
    }


def get_hair_shoe_acc(temp_range: str, precip: str, humidity: str) -> dict:
    """
    날씨 조건에 따른 헤어·신발·악세서리 추천
    """
    # ── 헤어 ───────────────────────────────────────
    if precip in ["rain", "shower", "sleet"]:
        if humidity == "high":
            hair = "업스타일(번, 포니테일)로 습기로 인한 헝클어짐 방지. 헤어 왁스로 잔머리 정리."
        else:
            hair = "비에 강한 업스타일 또는 모자 착용. 방습 헤어 에센스 필수."
    elif precip == "snow":
        hair = "모자(비니·울 햇) 착용 추천. 정전기 방지 트리트먼트 사용."
    elif temp_range in ["freezing", "very_cold"]:
        hair = "귀마개 또는 비니 착용 추천. 두피 보호를 위해 오일 에센스 마무리."
    elif temp_range in ["cold", "cool"]:
        hair = "자연스러운 웨이브나 스트레이트. 건조한 날씨엔 헤어 오일로 광택감 추가."
    elif temp_range in ["mild", "warm"]:
        hair = "가볍게 흘려 내린 스타일. 스프레이로 가볍게 고정."
    else:  # hot, very_hot
        hair = "업스타일(높은 번, 포니테일)로 시원하게. 두피 자외선 차단 스프레이 추천."

    # ── 신발 ───────────────────────────────────────
    if precip in ["rain", "shower"]:
        shoe = "방수 첼시 부츠 또는 방수 스니커즈. 화이트·스웨이드·캔버스 소재 피하기."
    elif precip == "sleet":
        shoe = "방수 앵클 부츠(발목 이상). 미끄럼 방지 밑창 필수."
    elif precip == "snow":
        shoe = "방수 워커 부츠(발목 이상). 스노우 부츠 또는 방수 트레킹 슈즈."
    elif temp_range == "freezing":
        shoe = "두꺼운 워커 부츠. 양말 2겹 착용으로 발 보온."
    elif temp_range == "very_cold":
        shoe = "앵클 부츠 또는 워커. 울 소재 두꺼운 양말 매치."
    elif temp_range in ["cold", "cool"]:
        shoe = "스니커즈 또는 앵클 부츠. 두꺼운 양말로 보온."
    elif temp_range in ["mild", "warm"]:
        shoe = "스니커즈, 로퍼, 옥스퍼드. 얇은 양말 또는 노 삭스."
    elif temp_range == "hot":
        shoe = "샌들, 슬리퍼, 슬립온. 발이 트이는 오픈토 스타일 추천."
    else:  # very_hot
        shoe = "샌들 또는 슬리퍼. 가능한 한 발이 많이 노출되는 스타일."

    # ── 악세서리 ────────────────────────────────────
    if precip in ["rain", "shower", "sleet", "snow"]:
        acc = "접이식 우산 또는 장우산 필수. 방수 소재 토트백 or 백팩 추천."
    elif temp_range in ["freezing", "very_cold"]:
        acc = "목도리(머플러) + 장갑 필수. 귀마개 선택. 핸드백보다 양손 자유로운 백팩 추천."
    elif temp_range in ["cold", "cool"]:
        acc = "얇은 스카프로 포인트 + 보온. 크로스백 또는 토트백."
    elif temp_range in ["mild", "warm"]:
        acc = "가벼운 쥬얼리(귀걸이, 목걸이) 1~2개. 미니백 또는 숄더백."
    else:  # hot, very_hot
        acc = "선글라스 + 챙 넓은 모자로 자외선 차단. 미니크로스백으로 가볍게."

    return {"hair": hair, "shoe": shoe, "acc": acc}