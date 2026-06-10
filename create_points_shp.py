"""
将经纬度坐标转为ArcGIS可用的点Shapefile
坐标来源: 用户提供的截图（DMS + 十进制度混合格式）
"""

import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import os

# ── 原始坐标（从截图解读） ──────────────────────────────────
# 前5个: 度分秒 (DMS)  →  转十进制度
# 后5个: 已是十进制度

def dms_to_dd(d, m, s):
    """度分秒 → 十进制度"""
    return d + m / 60.0 + s / 3600.0

points_raw = [
    # ID,  经度(lon),  纬度(lat),  备注
    (1,  dms_to_dd(109, 34,  6.89),  dms_to_dd(21, 33, 26.07),  "DMS"),
    (2,  dms_to_dd(109, 32, 55.04),  dms_to_dd(21, 32, 19.99),  "DMS"),
    (3,  dms_to_dd(109, 35, 35.60),  dms_to_dd(21, 32, 10.70),  "DMS"),
    (4,  dms_to_dd(109, 33, 18.44),  dms_to_dd(21, 31, 36.98),  "DMS"),
    (5,  dms_to_dd(109, 34, 33.86),  dms_to_dd(21, 34, 50.50),  "DMS"),
    (6,  109.5254651,  21.525143,   "DD"),
    (7,  109.54959,    21.5657878,  "DD"),
    (8,  109.534576,   21.58463,    "DD"),
    (9,  109.494766,   21.550592,   "DD"),
    (10, 109.553875,   21.60255,    "DD"),
]

# ── 构建 GeoDataFrame ────────────────────────────────────────
records = []
for pid, lon, lat, fmt in points_raw:
    records.append({
        "ID": pid,
        "Lon": round(lon, 6),
        "Lat": round(lat, 6),
        "Format": fmt,
        "geometry": Point(lon, lat),
    })

gdf = gpd.GeoDataFrame(records, crs="EPSG:4326")

# ── 输出 ─────────────────────────────────────────────────────
out_dir = os.path.dirname(os.path.abspath(__file__))
shp_path = os.path.join(out_dir, "sample_points.shp")
gdf.to_file(shp_path, encoding="utf-8")

print("=" * 60)
print(f"已生成Shapefile: {shp_path}")
print(f"共 {len(gdf)} 个点  |  CRS: EPSG:4326 (WGS84)")
print("=" * 60)
print(gdf[["ID", "Lon", "Lat", "Format"]].to_string(index=False))
print("=" * 60)
print("可直接在ArcGIS中通过 Add Data 加载 .shp 文件")
