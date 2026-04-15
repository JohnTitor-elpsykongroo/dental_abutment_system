# modules/abutment_designer.py
import json
import os
from datetime import datetime
from typing import Callable, Optional, Tuple

import igl
import numpy as np
import open3d as o3d
from utils.app_config import (
    RUNTIME_OUTPUT_DIR
)

# ============================================================
# 基础工具
# ============================================================
def _log(log_fn: Optional[Callable[[str], None]], text: str):
    if log_fn is not None:
        log_fn(text)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def read_mesh(path: str) -> Tuple[np.ndarray, np.ndarray]:
    vertices, triangles = igl.read_triangle_mesh(path)
    return np.asarray(vertices, dtype=np.float64), np.asarray(triangles, dtype=np.int32)


def write_mesh(path: str, vertices: np.ndarray, triangles: np.ndarray):
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.asarray(vertices, dtype=np.float64))
    mesh.triangles = o3d.utility.Vector3iVector(np.asarray(triangles, dtype=np.int32))
    mesh.compute_vertex_normals()
    ok = o3d.io.write_triangle_mesh(path, mesh)
    if not ok:
        raise RuntimeError("基台模型写出失败: {}".format(path))


def write_point_cloud(path: str, points: np.ndarray, color=(1.0, 0.0, 0.0)):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
    pcd.paint_uniform_color(color)
    ok = o3d.io.write_point_cloud(path, pcd)
    if not ok:
        raise RuntimeError("点云写出失败: {}".format(path))


def cartesian2polar(center_point: np.ndarray, vertices: np.ndarray):
    vectors = np.asarray(vertices, dtype=np.float64) - np.asarray(center_point, dtype=np.float64)
    x = vectors[:, 0]
    y = vectors[:, 1]
    z = vectors[:, 2]
    r = np.sqrt(x ** 2 + y ** 2)
    theta = np.arctan2(y, x)
    theta = np.mod(theta, 2 * np.pi)
    return r, theta, z


def angular_difference(angle: np.ndarray) -> np.ndarray:
    return np.mod(angle, 2 * np.pi)


def find_closest_indices(source_values: np.ndarray, target_values: np.ndarray) -> np.ndarray:
    source_values = np.asarray(source_values, dtype=np.float64).reshape(-1)
    target_values = np.asarray(target_values, dtype=np.float64).reshape(-1)

    out = []
    for t in target_values:
        diff = np.abs(angular_difference(source_values - t))
        diff = np.minimum(diff, 2 * np.pi - diff)
        out.append(int(np.argmin(diff)))
    return np.asarray(out, dtype=np.int32)


def find_closest_smaller_larger_indices(source_angles: np.ndarray, target_angles: np.ndarray):
    source_angles = np.asarray(source_angles, dtype=np.float64).reshape(-1)
    target_angles = np.asarray(target_angles, dtype=np.float64).reshape(-1)

    smaller_indices = []
    larger_indices = []

    for s in source_angles:
        pos = np.searchsorted(target_angles, s)

        if pos == 0:
            smaller_idx = len(target_angles) - 1
            larger_idx = 0
        elif pos == len(target_angles):
            smaller_idx = len(target_angles) - 1
            larger_idx = 0
        else:
            smaller_idx = pos - 1
            larger_idx = pos

        smaller_indices.append(smaller_idx)
        larger_indices.append(larger_idx)

    return (
        np.asarray(smaller_indices, dtype=np.int32),
        np.asarray(larger_indices, dtype=np.int32),
    )


def compute_radial_unit_vectors(center_point: np.ndarray,
                                points: np.ndarray,
                                epsilon: float = 1e-8) -> np.ndarray:
    vectors = np.asarray(points, dtype=np.float64) - np.asarray(center_point, dtype=np.float64)
    radial_vectors = vectors.copy()
    radial_vectors[:, 2] = 0.0
    norms = np.linalg.norm(radial_vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, epsilon)
    return radial_vectors / norms


def solve_arap(vertices: np.ndarray,
               triangles: np.ndarray,
               fixed_indices: np.ndarray,
               fixed_positions: np.ndarray) -> np.ndarray:
    fixed_indices = np.asarray(fixed_indices, dtype=np.int32).reshape(-1)
    fixed_positions = np.asarray(fixed_positions, dtype=np.float64)

    arap = igl.ARAP(vertices, triangles, 3, fixed_indices)
    deformed_vertices = arap.solve(fixed_positions, vertices)
    return np.asarray(deformed_vertices, dtype=np.float64)


# ============================================================
# JSON 输入
# ============================================================
def load_roi_and_control_indices(json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if "roi_indices" not in data:
        raise KeyError("ROI_indices.json 缺少 roi_indices 字段。")
    if "control_point_indices" not in data:
        raise KeyError("ROI_indices.json 缺少 control_point_indices 字段。")

    roi_indices = np.asarray(data["roi_indices"], dtype=np.int32).reshape(-1)
    control_point_indices = np.asarray(data["control_point_indices"], dtype=np.int32).reshape(-1)

    return roi_indices, control_point_indices


# ============================================================
# 控制线自动构造
# ============================================================
def build_control_lines_from_control_points(
    center_point: np.ndarray,
    abutment_vertices: np.ndarray,
    control_point_indices: np.ndarray,
    outer_radius_tol: float,
    outer_z_tol: float,
):
    """
    不再依赖 shoulder_edge.ply，
    而是直接从 control_point_indices 对应的顶点中自动构造上下两圈控制线。
    """
    control_vertices = abutment_vertices[control_point_indices]

    distances, theta, _ = cartesian2polar(
        center_point=center_point,
        vertices=control_vertices,
    )

    max_distance = np.max(distances)
    outer_ring_local_indices = np.where(
        np.abs(distances - max_distance) <= outer_radius_tol
    )[0]

    outer_ring_indices_in_abutment = control_point_indices[outer_ring_local_indices]
    outer_ring_vertices = abutment_vertices[outer_ring_indices_in_abutment]
    outer_ring_z = outer_ring_vertices[:, 2]
    outer_ring_theta = theta[outer_ring_local_indices]

    top_local_indices = np.where(
        np.abs(outer_ring_z - np.max(outer_ring_z)) <= outer_z_tol
    )[0]
    bottom_local_indices = np.where(
        np.abs(outer_ring_z - np.min(outer_ring_z)) <= outer_z_tol
    )[0]

    if len(top_local_indices) < 3 or len(bottom_local_indices) < 3:
        raise RuntimeError("control_point_indices 无法稳定分离出上下两圈控制点。")

    top_indices_in_abutment = outer_ring_indices_in_abutment[top_local_indices]
    bottom_indices_in_abutment = outer_ring_indices_in_abutment[bottom_local_indices]

    top_theta = outer_ring_theta[top_local_indices]
    bottom_theta = outer_ring_theta[bottom_local_indices]

    bottom_match_to_top = find_closest_indices(
        source_values=top_theta,
        target_values=bottom_theta,
    )

    sorted_top_order = np.argsort(top_theta)

    control_top_indices = top_indices_in_abutment[sorted_top_order]
    control_bottom_indices = bottom_indices_in_abutment[bottom_match_to_top[sorted_top_order]]
    control_top_theta = top_theta[sorted_top_order]

    control_lines = np.column_stack(
        (control_top_indices, control_bottom_indices)
    ).astype(np.int32)

    control_indices = np.unique(control_lines).astype(np.int32)

    return {
        "control_lines": control_lines,
        "control_indices": control_indices,
        "control_top_indices": control_top_indices,
        "control_bottom_indices": control_bottom_indices,
        "control_top_theta": control_top_theta,
    }


def sort_boundary_points_by_theta(center_point: np.ndarray, boundary_points: np.ndarray):
    _, theta, _ = cartesian2polar(center_point=center_point, vertices=boundary_points)
    sorted_order = np.argsort(theta)
    return {
        "points": boundary_points[sorted_order],
        "theta": theta[sorted_order],
        "sorted_order": sorted_order,
    }


def compute_target_vertices_from_cuff_boundary(
    center_point: np.ndarray,
    abutment_vertices: np.ndarray,
    control_lines: np.ndarray,
    control_top_theta: np.ndarray,
    cuff_reference_points: np.ndarray,
    emergence_height: float,
    compression: float,
    epsilon: float,
):
    cuff_boundary_sorted = sort_boundary_points_by_theta(center_point, cuff_reference_points)
    cuff_boundary_points = cuff_boundary_sorted["points"]
    cuff_boundary_theta = cuff_boundary_sorted["theta"]

    smaller_indices, larger_indices = find_closest_smaller_larger_indices(
        source_angles=control_top_theta,
        target_angles=cuff_boundary_theta,
    )

    cuff_boundary_smaller_theta = cuff_boundary_theta[smaller_indices]
    cuff_boundary_larger_theta = cuff_boundary_theta[larger_indices]

    delta_theta = angular_difference(cuff_boundary_larger_theta - cuff_boundary_smaller_theta)
    delta_theta[delta_theta == 0] += epsilon

    delta_ratio = (
        angular_difference(control_top_theta - cuff_boundary_smaller_theta) / delta_theta
    )

    smaller_boundary_vertices = cuff_boundary_points[smaller_indices]
    larger_boundary_vertices = cuff_boundary_points[larger_indices]
    delta_vector = larger_boundary_vertices - smaller_boundary_vertices

    boundary_matched_vertices = smaller_boundary_vertices + delta_vector * delta_ratio[:, np.newaxis]

    radial_unit_vectors = compute_radial_unit_vectors(
        center_point=center_point,
        points=boundary_matched_vertices,
        epsilon=epsilon,
    )
    radial_offset = compression * radial_unit_vectors
    height_offset = np.tile(np.array([0.0, 0.0, -emergence_height], dtype=np.float64),
                            (len(boundary_matched_vertices), 1))

    top_target_vertices = boundary_matched_vertices + radial_offset + height_offset

    delta_z = (
        abutment_vertices[control_lines[0, 0], 2] -
        abutment_vertices[control_lines[0, 1], 2]
    )
    bottom_target_vertices = top_target_vertices - np.array([0.0, 0.0, delta_z], dtype=np.float64)

    return {
        "boundary_matched_vertices": boundary_matched_vertices,
        "radial_unit_vectors": radial_unit_vectors,
        "top_target_vertices": top_target_vertices,
        "bottom_target_vertices": bottom_target_vertices,
        "delta_z": delta_z,
    }


def build_deformation_constraints(
    abutment_vertices: np.ndarray,
    roi_indices: np.ndarray,
    control_indices: np.ndarray,
    control_lines: np.ndarray,
    top_target_vertices: np.ndarray,
    bottom_target_vertices: np.ndarray,
):
    deformed_target_vertices = abutment_vertices.copy()
    deformed_target_vertices[control_lines[:, 0]] = top_target_vertices
    deformed_target_vertices[control_lines[:, 1]] = bottom_target_vertices

    vertex_labels = np.zeros(len(abutment_vertices), dtype=np.int32)
    vertex_labels[roi_indices] = -1
    vertex_labels[control_indices] = 1

    fixed_indices = np.flatnonzero(vertex_labels >= 0).astype(np.int32)
    fixed_positions = abutment_vertices[fixed_indices].copy()

    control_mask_on_fixed = vertex_labels[fixed_indices] == 1
    fixed_positions[control_mask_on_fixed] = deformed_target_vertices[fixed_indices[control_mask_on_fixed]]

    return {
        "deformed_target_vertices": deformed_target_vertices,
        "vertex_labels": vertex_labels,
        "fixed_indices": fixed_indices,
        "fixed_positions": fixed_positions,
    }


# ============================================================
# 主模块
# ============================================================
class AbutmentDesigner:
    def __init__(self):
        self.name = "AbutmentDesigner"

    def run(
        self,
        standard_abutment_path: str,
        roi_indices_json_path: str,
        match_result: dict,
        cuff_result: dict,
        params: dict,
        gingiva_mesh_path: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        try:
            if cuff_result is None or cuff_result.get("status") != "success":
                raise RuntimeError("cuff_result 不可用，请先完成袖口识别。")

            reference_curve_txt_path = cuff_result.get("output", {}).get("reference_curve_txt_path")
            if not reference_curve_txt_path or not os.path.exists(reference_curve_txt_path):
                raise RuntimeError("未找到 cuff 参考边界点文件。")

            epsilon = float(params.get("epsilon", 1e-6))
            center_point = np.asarray(params.get("center_point", [0.0, 0.0, 0.0]), dtype=np.float64)

            emergence_height = float(params.get("emergence_height", 1.0))
            compression = float(params.get("pressure_offset", 0.3))
            outer_radius_tol = float(params.get("outer_radius_tol", 0.01))
            outer_z_tol = float(params.get("outer_z_tol", 0.01))

            out_dir = os.path.join(str(RUNTIME_OUTPUT_DIR), "abutment_design")
            ensure_dir(out_dir)

            _log(log_callback, "[基台生成] 读取标准基台")
            abutment_vertices, abutment_triangles = read_mesh(standard_abutment_path)

            _log(log_callback, "[基台生成] 读取 ROI 与控制点索引 JSON")
            roi_indices, control_point_indices = load_roi_and_control_indices(roi_indices_json_path)

            _log(log_callback, "[基台生成] ROI 顶点数: {}".format(len(roi_indices)))
            _log(log_callback, "[基台生成] 控制点索引数: {}".format(len(control_point_indices)))

            control_data = build_control_lines_from_control_points(
                center_point=center_point,
                abutment_vertices=abutment_vertices,
                control_point_indices=control_point_indices,
                outer_radius_tol=outer_radius_tol,
                outer_z_tol=outer_z_tol,
            )
            control_lines = control_data["control_lines"]
            control_indices = control_data["control_indices"]
            control_top_theta = control_data["control_top_theta"]

            _log(log_callback, "[基台生成] 控制点顶点数: {}".format(len(control_indices)))
            _log(log_callback, "[基台生成] 控制点上下连线数: {}".format(len(control_lines)))

            cuff_reference_points = np.loadtxt(reference_curve_txt_path)
            if cuff_reference_points.ndim == 1:
                cuff_reference_points = cuff_reference_points.reshape(1, -1)
            cuff_reference_points = np.asarray(cuff_reference_points[:, :3], dtype=np.float64)

            _log(log_callback, "[基台生成] 参考边界点数: {}".format(len(cuff_reference_points)))
            _log(log_callback, "[基台生成] 穿龈高度: {:.4f}".format(emergence_height))
            _log(log_callback, "[基台生成] 穿龈压迫量: {:.4f}".format(compression))

            target_data = compute_target_vertices_from_cuff_boundary(
                center_point=center_point,
                abutment_vertices=abutment_vertices,
                control_lines=control_lines,
                control_top_theta=control_top_theta,
                cuff_reference_points=cuff_reference_points,
                emergence_height=emergence_height,
                compression=compression,
                epsilon=epsilon,
            )

            top_target_vertices = target_data["top_target_vertices"]
            bottom_target_vertices = target_data["bottom_target_vertices"]

            deformation_constraints = build_deformation_constraints(
                abutment_vertices=abutment_vertices,
                roi_indices=roi_indices,
                control_indices=control_indices,
                control_lines=control_lines,
                top_target_vertices=top_target_vertices,
                bottom_target_vertices=bottom_target_vertices,
            )

            _log(log_callback, "[基台生成] 执行 ARAP 变形")
            new_abutment_vertices = solve_arap(
                vertices=abutment_vertices,
                triangles=abutment_triangles,
                fixed_indices=deformation_constraints["fixed_indices"],
                fixed_positions=deformation_constraints["fixed_positions"],
            )

            output_model_path = os.path.join(out_dir, "deformed_abutment.ply")
            top_target_path = os.path.join(out_dir, "top_target_vertices.ply")
            bottom_target_path = os.path.join(out_dir, "bottom_target_vertices.ply")

            write_mesh(output_model_path, new_abutment_vertices, abutment_triangles)
            write_point_cloud(top_target_path, top_target_vertices, color=(1.0, 0.0, 0.0))
            write_point_cloud(bottom_target_path, bottom_target_vertices, color=(1.0, 0.5, 0.0))

            _log(log_callback, "[基台生成] 已输出变形后基台: {}".format(output_model_path))

            return {
                "module": self.name,
                "status": "success",
                "message": "个性化基台形态生成完成",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "standard_abutment_path": standard_abutment_path,
                    "roi_indices_json_path": roi_indices_json_path,
                    "reference_curve_txt_path": reference_curve_txt_path,
                    "gingiva_mesh_path": gingiva_mesh_path,
                },
                "params": params,
                "output": {
                    "output_model_path": output_model_path,
                    "top_target_vertices_path": top_target_path,
                    "bottom_target_vertices_path": bottom_target_path,
                    "roi_vertex_count": int(len(roi_indices)),
                    "control_point_count": int(len(control_indices)),
                    "control_line_count": int(len(control_lines)),
                    "summary": {
                        "emergence_height": emergence_height,
                        "pressure_offset": compression,
                        "outer_radius_tol": outer_radius_tol,
                        "outer_z_tol": outer_z_tol,
                    }
                }
            }

        except Exception as e:
            if log_callback is not None:
                log_callback("[基台生成][错误] {}".format(str(e)))

            return {
                "module": self.name,
                "status": "failed",
                "message": "个性化基台形态生成失败: {}".format(str(e)),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "standard_abutment_path": standard_abutment_path,
                    "roi_indices_json_path": roi_indices_json_path,
                    "gingiva_mesh_path": gingiva_mesh_path,
                },
                "params": params,
                "output": None,
            }