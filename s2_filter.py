import json
import s2sphere
import logging

logging.basicConfig(level=logging.INFO)

TARGET_S2_LEVEL = 16

def process_portals(input_file="raw_portals.json", output_file="pois.json"):
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        logging.error(f"❌ 找不到原始情報檔 {input_file}！")
        return

    s2_grid_memory = {}
    anti_survivors = [] # [V2 新增] 用來裝「被淘汰的影子點位」
    
    logging.info(f"📥 載入原始 Ingress 點位: {len(raw_data)} 個")

    for portal in raw_data:
        lat = portal.get("lat") or portal.get("latitude")
        lon = portal.get("lng") or portal.get("longitude")
        name = portal.get("name", "Unknown POI")

        if not lat or not lon:
            continue

        p1 = s2sphere.LatLng.from_degrees(float(lat), float(lon))
        cell_id = s2sphere.CellId.from_lat_lng(p1).parent(TARGET_S2_LEVEL)
        cell_token = cell_id.to_token()

        if cell_token not in s2_grid_memory:
            # 這是上一輪活下來的點 (也就是你說的空包彈)
            s2_grid_memory[cell_token] = {
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "s2_cell": cell_token
            }
        else:
            # [反向邏輯] 網格裡已經有空包彈了？太好了，那這個被擠掉的點極有可能就是真正的蘑菇！
            anti_survivors.append({
                "name": name,
                "lat": float(lat),
                "lon": float(lon),
                "s2_cell": cell_token
            })

    logging.info(f"🛡️ 反向過濾完畢！")
    logging.info(f"❌ 捨棄了 {len(s2_grid_memory)} 個首選空包彈")
    logging.info(f"🍄 撈回了 {len(anti_survivors)} 個影子點位 (準備裝填)")

    # 這次我們把被淘汰的「影子點位」輸出成雷達要讀的 pois.json
    output_data = {"pois": anti_survivors}
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        
    logging.info(f"✅ 反向情報已輸出至 {output_file}，請重啟戰情室雷達！")

if __name__ == "__main__":
    process_portals()