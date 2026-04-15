# modules/cuff_segmenter.py
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import open3d as o3d
from scipy.interpolate import splprep, splev

try:
    import igl
except Exception:
    igl = None


# ============================================================
# Config
# ============================================================
@dataclass
class CuffConfig:
    loop_select_mode: str = "longest"   # "longest" / "manual"
    target_loop_id: int = 0

    reference_num_samples: int = 240
    reference_smooth_factor: float = 0.6
    reference_spline_degree: int = 3

    display_offset_on_gingiva: float = 0.05
    save_outputs: bool = True
    output_dir: str = os.path.join("outputs", "cuff_segment")


# ============================================================
# Utils
# ============================================================
def _log(log_fn: Optional[Callable[[str], None]], text: str):
    if log_fn is not None:
        log_fn(text)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def read_mesh(path: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    优先用 igl 读取，失败则回退到 Open3D。
    """
    if igl is not None:
        try:
            vertices, triangles = igl.read_triangle_mesh(path)
            vertices = np.asarray(vertices, dtype=np.float64)
            triangles = np.asarray(triangles, dtype=np.int32)
            if len(vertices) > 0 and len(triangles) > 0:
                return vertices, triangles
        except Exception:
            pass

    mesh = o3d.io.read_triangle_mesh(path)
    if mesh is None or len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
        raise ValueError("无法读取三角网格文件: {}".format(path))

    return (
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.triangles, dtype=np.int32),
    )


def make_point_cloud(points: np.ndarray,
                     color: Tuple[float, float, float]) -> o3d.geometry.PointCloud:
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    pcd.paint_uniform_color(color)
    return pcd


# ============================================================
# Boundary extraction
# ============================================================
def extract_boundary_edges(triangles: np.ndarray) -> List[Tuple[int, int]]:
    edge_count = defaultdict(int)
    triangles = np.asarray(triangles, dtype=np.int32)

    for tri in triangles:
        a, b, c = tri
        edges = [
            tuple(sorted((a, b))),
            tuple(sorted((b, c))),
            tuple(sorted((c, a))),
        ]
        for edge in edges:
            edge_count[edge] += 1

    return [edge for edge, count in edge_count.items() if count == 1]


def build_boundary_loops(boundary_edges: Sequence[Tuple[int, int]]) -> List[np.ndarray]:
    adjacency = defaultdict(list)
    for u, v in boundary_edges:
        adjacency[u].append(v)
        adjacency[v].append(u)

    visited_edges = set()
    loops = []

    def edge_key(a: int, b: int) -> Tuple[int, int]:
        return tuple(sorted((a, b)))

    for u, v in boundary_edges:
        key = edge_key(u, v)
        if key in visited_edges:
            continue

        loop = [u, v]
        visited_edges.add(key)
        prev, curr = u, v

        while True:
            neighbors = adjacency[curr]
            candidates = [x for x in neighbors if x != prev]
            if len(candidates) == 0:
                break

            next_vertex = None
            for candidate in candidates:
                next_key = edge_key(curr, candidate)
                if next_key not in visited_edges:
                    next_vertex = candidate
                    break

            if next_vertex is None:
                break

            loop.append(next_vertex)
            visited_edges.add(edge_key(curr, next_vertex))
            prev, curr = curr, next_vertex

            if curr == loop[0]:
                break

        if len(loop) > 2 and loop[-1] == loop[0]:
            loop = loop[:-1]

        if len(loop) >= 3:
            loops.append(np.asarray(loop, dtype=np.int32))

    return loops


def remove_duplicate_consecutive_points(points: np.ndarray, tol: float = 1e-8) -> np.ndarray:
    points = np.asarray(points, dtype=np.float64)
    if len(points) <= 1:
        return points

    kept = [points[0]]
    for i in range(1, len(points)):
        if np.linalg.norm(points[i] - kept[-1]) > tol:
            kept.append(points[i])

    kept = np.asarray(kept, dtype=np.float64)
    if len(kept) > 2 and np.linalg.norm(kept[0] - kept[-1]) <= tol:
        kept = kept[:-1]
    return kept


def resample_closed_curve(points: np.ndarray, num_samples: int) -> np.ndarray:
    points = remove_duplicate_consecutive_points(points)
    points_closed = np.vstack([points, points[0]])
    seg_lengths = np.linalg.norm(np.diff(points_closed, axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total_length = cumulative[-1]

    target_lengths = np.linspace(0.0, total_length, num_samples + 1)[:-1]
    sampled = np.zeros((num_samples, 3), dtype=np.float64)
    for dim in range(3):
        sampled[:, dim] = np.interp(target_lengths, cumulative, points_closed[:, dim])
    return sampled


def smooth_boundary_loop(loop_points: np.ndarray,
                         num_samples: int,
                         smooth_factor: float,
                         spline_degree: int) -> Tuple[np.ndarray, np.ndarray]:
    ordered_points = remove_duplicate_consecutive_points(loop_points)

    if len(ordered_points) < 4:
        reference_points = resample_closed_curve(ordered_points, num_samples=num_samples)
        return ordered_points, reference_points

    points_closed = np.vstack([ordered_points, ordered_points[0]])
    seg_lengths = np.linalg.norm(np.diff(points_closed, axis=0), axis=1)
    valid_mask = seg_lengths > 1e-10
    if not np.all(valid_mask):
        keep_mask = np.concatenate([[True], valid_mask])
        points_closed = points_closed[keep_mask]
        seg_lengths = np.linalg.norm(np.diff(points_closed, axis=0), axis=1)

    chord = np.concatenate([[0.0], np.cumsum(seg_lengths)])
    total_length = chord[-1]
    u = chord / max(total_length, 1e-12)

    avg_spacing = np.median(seg_lengths) if len(seg_lengths) > 0 else 1.0
    smooth_value = smooth_factor * len(ordered_points) * (avg_spacing ** 2)
    degree = min(spline_degree, len(ordered_points) - 1)

    try:
        spline, _ = splprep(
            [points_closed[:, 0], points_closed[:, 1], points_closed[:, 2]],
            u=u,
            s=smooth_value,
            per=True,
            k=degree,
        )
        dense_n = max(2000, num_samples * 20)
        u_dense = np.linspace(0.0, 1.0, dense_n, endpoint=False)
        dense_curve = np.vstack(splev(u_dense, spline)).T
        reference_points = resample_closed_curve(dense_curve, num_samples=num_samples)
        return ordered_points, reference_points
    except Exception:
        reference_points = resample_closed_curve(ordered_points, num_samples=num_samples)
        return ordered_points, reference_points


def select_cuff_loop(
    cuff_vertices: np.ndarray,
    cuff_triangles: np.ndarray,
    loop_select_mode: str,
    target_loop_id: int,
    reference_num_samples: int,
    reference_smooth_factor: float,
    reference_spline_degree: int,
) -> Dict:
    boundary_edges = extract_boundary_edges(cuff_triangles)
    loops = build_boundary_loops(boundary_edges)
    if len(loops) == 0:
        raise RuntimeError("未从 cuff 网格中检测到边界环。")

    loop_lengths = [len(loop) for loop in loops]

    if loop_select_mode == "longest":
        loop_id = int(np.argmax(loop_lengths))
    elif loop_select_mode == "manual":
        loop_id = int(target_loop_id)
    else:
        raise ValueError("loop_select_mode 仅支持 'longest' 或 'manual'。")

    if not (0 <= loop_id < len(loops)):
        raise IndexError("选中的 target_loop_id={} 超出范围。".format(loop_id))

    selected_indices = loops[loop_id]
    selected_points = cuff_vertices[selected_indices]
    ordered_points, reference_points = smooth_boundary_loop(
        selected_points,
        num_samples=reference_num_samples,
        smooth_factor=reference_smooth_factor,
        spline_degree=reference_spline_degree,
    )

    return {
        "boundary_edges": boundary_edges,
        "loops": loops,
        "loop_id": loop_id,
        "selected_indices": selected_indices,
        "ordered_points": ordered_points,
        "reference_points": reference_points,
        "loop_lengths": loop_lengths,
    }


# ============================================================
# Project to gingiva surface
# ============================================================
def project_points_to_mesh_surface(
    query_points: np.ndarray,
    mesh_vertices: np.ndarray,
    mesh_triangles: np.ndarray,
    display_offset: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    query_points = np.asarray(query_points, dtype=np.float64)
    mesh_vertices = np.asarray(mesh_vertices, dtype=np.float64)
    mesh_triangles = np.asarray(mesh_triangles, dtype=np.int32)

    legacy_mesh = o3d.geometry.TriangleMesh()
    legacy_mesh.vertices = o3d.utility.Vector3dVector(mesh_vertices)
    legacy_mesh.triangles = o3d.utility.Vector3iVector(mesh_triangles)
    legacy_mesh.compute_vertex_normals()

    try:
        tmesh = o3d.t.geometry.TriangleMesh.from_legacy(legacy_mesh)
        scene = o3d.t.geometry.RaycastingScene()
        _ = scene.add_triangles(tmesh)

        queries = o3d.core.Tensor(query_points.astype(np.float32), dtype=o3d.core.Dtype.Float32)
        ans = scene.compute_closest_points(queries)

        projected_points = ans["points"].numpy().astype(np.float64)
        if "primitive_normals" in ans:
            normals = ans["primitive_normals"].numpy().astype(np.float64)
        else:
            vertices = np.asarray(legacy_mesh.vertices)
            vnormals = np.asarray(legacy_mesh.vertex_normals)
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(vertices)
            kdtree = o3d.geometry.KDTreeFlann(pcd)
            idx = []
            for p in projected_points:
                _, inds, _ = kdtree.search_knn_vector_3d(p, 1)
                idx.append(inds[0])
            normals = vnormals[np.asarray(idx, dtype=np.int32)]

    except Exception:
        # 回退到最近顶点投影
        vertices = np.asarray(legacy_mesh.vertices)
        vnormals = np.asarray(legacy_mesh.vertex_normals)
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(vertices)
        kdtree = o3d.geometry.KDTreeFlann(pcd)

        idx = []
        for p in query_points:
            _, inds, _ = kdtree.search_knn_vector_3d(p, 1)
            idx.append(inds[0])

        idx = np.asarray(idx, dtype=np.int32)
        projected_points = vertices[idx]
        normals = vnormals[idx]

    norms = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(norms, 1e-12)
    display_points = projected_points + display_offset * normals
    return projected_points, normals, display_points


# ============================================================
# Module
# ============================================================
class CuffSegmenter:
    """
    参考你给的 cuff_boundary_compare.py：
    - 从 cuff 网格提取边界边
    - 构造边界环
    - 选取目标边界环
    - 平滑重采样得到参考边界
    - 将边界投影到 gingiva_mesh 表面用于界面显示
    """

    def __init__(self):
        self.name = "CuffSegmenter"

    def _build_config(self, params: dict) -> CuffConfig:
        cfg = CuffConfig()

        cfg.loop_select_mode = params.get("loop_select_mode", "longest")
        cfg.target_loop_id = int(params.get("target_loop_id", 0))
        cfg.reference_num_samples = int(params.get("reference_num_samples", 240))
        cfg.reference_smooth_factor = float(params.get("reference_smooth_factor", 0.6))
        cfg.reference_spline_degree = int(params.get("reference_spline_degree", 3))
        cfg.display_offset_on_gingiva = float(params.get("display_offset_on_gingiva", 0.05))
        cfg.save_outputs = bool(params.get("save_outputs", True))
        cfg.output_dir = params.get("output_dir", os.path.join("outputs", "cuff_segment"))

        return cfg

    def run(
        self,
        gingiva_mesh_path: str,
        cuff_data_path: str,
        params: dict,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        try:
            cfg = self._build_config(params)
            ensure_dir(cfg.output_dir)

            _log(log_callback, "[袖口识别] 读取牙齿模型与袖口模型")
            gingiva_vertices, gingiva_triangles = read_mesh(gingiva_mesh_path)
            cuff_vertices, cuff_triangles = read_mesh(cuff_data_path)

            _log(log_callback, "[袖口识别] cuff 顶点数: {}, 面片数: {}".format(
                len(cuff_vertices), len(cuff_triangles)
            ))
            _log(log_callback, "[袖口识别] gingiva 顶点数: {}, 面片数: {}".format(
                len(gingiva_vertices), len(gingiva_triangles)
            ))

            _log(log_callback, "[袖口识别] 提取边界环")
            cuff_result = select_cuff_loop(
                cuff_vertices=cuff_vertices,
                cuff_triangles=cuff_triangles,
                loop_select_mode=cfg.loop_select_mode,
                target_loop_id=cfg.target_loop_id,
                reference_num_samples=cfg.reference_num_samples,
                reference_smooth_factor=cfg.reference_smooth_factor,
                reference_spline_degree=cfg.reference_spline_degree,
            )

            raw_boundary_points = cuff_result["ordered_points"]
            reference_boundary_points = cuff_result["reference_points"]

            _log(log_callback, "[袖口识别] 检测到边界环数量: {}".format(len(cuff_result["loops"])))
            _log(log_callback, "[袖口识别] 当前选中边界环编号: {}".format(cuff_result["loop_id"]))
            _log(log_callback, "[袖口识别] 原始边界点数: {}".format(len(raw_boundary_points)))
            _log(log_callback, "[袖口识别] 参考边界点数: {}".format(len(reference_boundary_points)))

            _log(log_callback, "[袖口识别] 投影边界到牙齿模型表面")
            _, _, raw_display_points = project_points_to_mesh_surface(
                raw_boundary_points,
                gingiva_vertices,
                gingiva_triangles,
                display_offset=cfg.display_offset_on_gingiva,
            )
            _, _, ref_display_points = project_points_to_mesh_surface(
                reference_boundary_points,
                gingiva_vertices,
                gingiva_triangles,
                display_offset=cfg.display_offset_on_gingiva,
            )

            raw_boundary_txt = os.path.join(cfg.output_dir, "raw_boundary_points.txt")
            ref_boundary_txt = os.path.join(cfg.output_dir, "reference_boundary_points.txt")
            raw_display_txt = os.path.join(cfg.output_dir, "raw_boundary_display_on_gingiva.txt")
            ref_display_txt = os.path.join(cfg.output_dir, "reference_boundary_display_on_gingiva.txt")

            raw_boundary_ply = os.path.join(cfg.output_dir, "raw_boundary_points.ply")
            ref_boundary_ply = os.path.join(cfg.output_dir, "reference_boundary_points.ply")
            raw_display_ply = os.path.join(cfg.output_dir, "raw_boundary_display_on_gingiva.ply")
            ref_display_ply = os.path.join(cfg.output_dir, "reference_boundary_display_on_gingiva.ply")

            if cfg.save_outputs:
                np.savetxt(raw_boundary_txt, raw_boundary_points, fmt="%.8f")
                np.savetxt(ref_boundary_txt, reference_boundary_points, fmt="%.8f")
                np.savetxt(raw_display_txt, raw_display_points, fmt="%.8f")
                np.savetxt(ref_display_txt, ref_display_points, fmt="%.8f")

                o3d.io.write_point_cloud(
                    raw_boundary_ply,
                    make_point_cloud(raw_boundary_points, color=(1.0, 0.0, 0.0))
                )
                o3d.io.write_point_cloud(
                    ref_boundary_ply,
                    make_point_cloud(reference_boundary_points, color=(0.0, 0.2, 1.0))
                )
                o3d.io.write_point_cloud(
                    raw_display_ply,
                    make_point_cloud(raw_display_points, color=(1.0, 0.0, 0.0))
                )
                o3d.io.write_point_cloud(
                    ref_display_ply,
                    make_point_cloud(ref_display_points, color=(0.0, 0.2, 1.0))
                )

                _log(log_callback, "[袖口识别] 已输出边界文件到: {}".format(cfg.output_dir))

            result = {
                "module": self.name,
                "status": "success",
                "message": "袖口边缘提取与参考边界重建完成",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "gingiva_mesh_path": gingiva_mesh_path,
                    "cuff_data_path": cuff_data_path,
                },
                "params": params,
                "output": {
                    "loop_count": len(cuff_result["loops"]),
                    "selected_loop_id": cuff_result["loop_id"],
                    "loop_lengths": cuff_result["loop_lengths"],
                    "boundary_point_count": len(raw_boundary_points),
                    "reference_point_count": len(reference_boundary_points),

                    # 原始 cuff 边缘顶点（原始位置）
                    "boundary_points_path": raw_boundary_ply,
                    "boundary_points_txt_path": raw_boundary_txt,

                    # 重建后的参考边界（后续第五章可直接用）
                    "reference_curve_path": ref_boundary_ply,
                    "reference_curve_txt_path": ref_boundary_txt,

                    # 贴附到牙齿表面、用于 GUI 显示的边界顶点
                    "boundary_display_path": raw_display_ply,
                    "boundary_display_txt_path": raw_display_txt,

                    # 贴附到牙齿表面的参考边界（后续可扩展显示）
                    "reference_display_path": ref_display_ply,
                    "reference_display_txt_path": ref_display_txt,

                    # 保留兼容字段
                    "segmentation_mask_path": raw_display_ply,
                }
            }
            return result

        except Exception as e:
            if log_callback is not None:
                log_callback("[袖口识别][错误] {}".format(str(e)))

            return {
                "module": self.name,
                "status": "failed",
                "message": "袖口识别失败: {}".format(str(e)),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "gingiva_mesh_path": gingiva_mesh_path,
                    "cuff_data_path": cuff_data_path,
                },
                "params": params,
                "output": None,
            }