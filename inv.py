import math

def calculate_order_quantity(current_stock, production_plan, safety_stock, moq=0, lot_size=1):
    # 1. 순수 필요 수량 계산
    required_qty = (production_plan + safety_stock) - current_stock
    
    # 2. 재고가 충분할 경우 발주 불필요 (0 반환)
    if required_qty <= 0:
        return 0
        
    # 3. 최소 발주 수량(MOQ) 적용
    order_qty = max(required_qty, moq)
    
    # 4. 포장 단위(LOT Size) 적용 (부족하지 않도록 올림 처리)
    order_qty = math.ceil(order_qty / lot_size) * lot_size
    
    return order_qty

# --- 실무 데이터 적용 예시 ---

# 예시 1: 블로워 모터 (Blower Motor)
motor_order = calculate_order_quantity(
    current_stock=1500,    # 현재 보유 재고
    production_plan=5000,  # 향후 생산 소요 수량
    safety_stock=1000,     # 유지해야 할 안전 재고
    moq=2000,              # 협력사 최소 생산/발주 수량
    lot_size=50            # 박스/파렛트당 단위
)

# 예시 2: 스틸 강판 (Steel Sheet)
steel_order = calculate_order_quantity(
    current_stock=800,
    production_plan=2000,
    safety_stock=500,
    moq=1000,
    lot_size=100
)

print(f"블로워 모터 발주 대상 수량: {motor_order}개") 
print(f"스틸 강판 발주 대상 수량: {steel_order}장")
