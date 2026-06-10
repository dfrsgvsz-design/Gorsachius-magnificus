# -*- coding: utf-8 -*-
"""Step 2: 数据预处理 - 统一投影、重采样到 2010 网格、派生驱动因子。"""
import os
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, calculate_default_transform

DATA = r'E:\大学\万物春'
OUT = r'E:\大学\万物春\erci\_plus_workspace'
os.makedirs(OUT, exist_ok=True)

# 参考网格：2010.tif
ref_path = os.path.join(DATA, '横州市_2010.tif')
with rasterio.open(ref_path) as ref:
    ref_crs = ref.crs
    ref_transform = ref.transform
    ref_shape = ref.shape
    ref_bounds = ref.bounds
    ref_nodata = ref.nodata
    print(f'参考网格: {ref_shape}, CRS={ref_crs}, bounds={ref_bounds}')


def reproj_to_ref(src_path, dst_path, resampling=Resampling.nearest, src_nodata=None):
    """重投影到 ref 网格。"""
    with rasterio.open(src_path) as src:
        if src_nodata is None:
            src_nodata = src.nodata
        dst_arr = np.full(ref_shape, src_nodata if src_nodata is not None else 0, dtype=src.dtypes[0])
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_transform,
            dst_crs=ref_crs,
            resampling=resampling,
            src_nodata=src_nodata,
            dst_nodata=src_nodata,
        )
        profile = src.profile.copy()
        profile.update({
            'crs': ref_crs,
            'transform': ref_transform,
            'width': ref_shape[1],
            'height': ref_shape[0],
            'nodata': src_nodata,
        })
        with rasterio.open(dst_path, 'w', **profile) as dst:
            dst.write(dst_arr, 1)
    print(f'  [OK] {os.path.basename(dst_path)} <- {os.path.basename(src_path)}')


# 1. 2010/2015/2020 tif 直接复制到工作区
import shutil
for y in [2010, 2015, 2020]:
    src = os.path.join(DATA, f'横州市_{y}.tif')
    dst = os.path.join(OUT, f'lu_{y}.tif')
    if not os.path.exists(dst):
        shutil.copy(src, dst)
        print(f'  [COPY] lu_{y}.tif')

# 2. 重投影 2025 tif -> EPSG:4326 + ref 网格
print('\n[重投影 2025]')
reproj_to_ref(
    os.path.join(DATA, '横州市_2025.tif'),
    os.path.join(OUT, 'lu_2025.tif'),
    resampling=Resampling.nearest,
    src_nodata=15,
)

# 3. 重投影 DEM -> ref 网格（双线性）
print('\n[重投影 DEM]')
reproj_to_ref(
    os.path.join(DATA, '横州市_dem.tif'),
    os.path.join(OUT, 'dem.tif'),
    resampling=Resampling.bilinear,
    src_nodata=-32768,
)

# 4. 派生坡度/坡向（从 DEM）
print('\n[派生坡度/坡向]')
import math
with rasterio.open(os.path.join(OUT, 'dem.tif')) as src:
    dem = src.read(1).astype(float)
    profile = src.profile.copy()
    # 用度作为分辨率，但近似估算米：1°≈111km, 0.000269°≈30m
    res_m = 30.0  # 近似
    # Sobel 梯度
    from scipy.ndimage import sobel
    dz_dx = sobel(dem, axis=1) / (8 * res_m)
    dz_dy = sobel(dem, axis=0) / (8 * res_m)
    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    aspect = np.degrees(np.arctan2(dz_dy, -dz_dx))
    aspect = np.where(aspect < 0, aspect + 360, aspect)
    # nodata mask
    nodata_mask = (dem == -32768)
    slope[nodata_mask] = -1
    aspect[nodata_mask] = -1

    profile.update(dtype='float32', nodata=-1)
    with rasterio.open(os.path.join(OUT, 'slope.tif'), 'w', **profile) as dst:
        dst.write(slope.astype(np.float32), 1)
    with rasterio.open(os.path.join(OUT, 'aspect.tif'), 'w', **profile) as dst:
        dst.write(aspect.astype(np.float32), 1)
    print(f'  [OK] slope.tif, aspect.tif')
    print(f'  slope range: {slope[~nodata_mask].min():.2f} ~ {slope[~nodata_mask].max():.2f}')

# 5. 距水域距离 + 距建设用地距离（从 2010 lu 派生，因为是基期）
print('\n[派生距离因子]')
from scipy.ndimage import distance_transform_edt
with rasterio.open(os.path.join(OUT, 'lu_2010.tif')) as src:
    lu2010 = src.read(1)
    profile = src.profile.copy()
    # 距水域距离：gridcode=5 为水域
    water_mask = (lu2010 == 5)
    if water_mask.sum() > 0:
        dist_water = distance_transform_edt(~water_mask).astype(np.float32) * res_m
    else:
        dist_water = np.full(lu2010.shape, 0, dtype=np.float32)
    # 距建设用地距离：gridcode=8
    built_mask = (lu2010 == 8)
    if built_mask.sum() > 0:
        dist_built = distance_transform_edt(~built_mask).astype(np.float32) * res_m
    else:
        dist_built = np.full(lu2010.shape, 0, dtype=np.float32)

    profile.update(dtype='float32', nodata=-1)
    with rasterio.open(os.path.join(OUT, 'dist_water.tif'), 'w', **profile) as dst:
        dst.write(dist_water, 1)
    with rasterio.open(os.path.join(OUT, 'dist_built.tif'), 'w', **profile) as dst:
        dst.write(dist_built, 1)
    print(f'  [OK] dist_water.tif (range: {dist_water.min():.1f} ~ {dist_water.max():.1f} m)')
    print(f'  [OK] dist_built.tif (range: {dist_built.min():.1f} ~ {dist_built.max():.1f} m)')

# 6. 距中心距离（简单几何中心）
with rasterio.open(os.path.join(OUT, 'lu_2010.tif')) as src:
    profile = src.profile.copy()
    h, w = src.shape
    cy, cx = h // 2, w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    dist_center = (np.sqrt((yy - cy)**2 + (xx - cx)**2) * res_m).astype(np.float32)
    profile.update(dtype='float32', nodata=-1)
    with rasterio.open(os.path.join(OUT, 'dist_center.tif'), 'w', **profile) as dst:
        dst.write(dist_center, 1)
    print(f'  [OK] dist_center.tif (range: 0 ~ {dist_center.max():.1f} m)')

# 7. 摘要
print('\n[预处理摘要]')
for fn in sorted(os.listdir(OUT)):
    path = os.path.join(OUT, fn)
    if fn.endswith('.tif'):
        with rasterio.open(path) as src:
            arr = src.read(1)
            valid = arr[arr != src.nodata]
            if valid.size > 0:
                print(f'  {fn:20}: shape={src.shape}, dtype={src.dtypes[0]:7}, '
                      f'min={float(valid.min()):.2f}, max={float(valid.max()):.2f}, '
                      f'valid_pix={valid.size}/{arr.size}')

print('\nDone.')
