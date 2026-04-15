# modules/scanbody_matcher.py
import copy
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional, Tuple

import numpy as np
import open3d as o3d


# ============================================================
# Configuration
# ============================================================
@dataclass
class Config:
    # ---------------- Paths ----------------
    source_path: str = ""          # standard scanbody
    target_path: str = ""          # intraoral scan scanbody

    # ---------------- Sampling / preprocessing ----------------
    source_sample_points: int = 12000
    target_sample_points: int = 12000
    voxel_size: float = 0.25
    sor_nb_neighbors: int = 20
    sor_std_ratio: float = 1.5

    # ---------------- FPFH coarse registration ----------------
    normal_radius_factor: float = 2.0
    fpfh_radius_factor: float = 5.0
    ransac_distance_factor: float = 1.5
    ransac_n: int = 4
    ransac_max_iteration: int = 100000
    ransac_max_validation: int = 500

    # ---------------- Correspondence generation ----------------
    correspondence_distance_factor: float = 1.5

    # ---------------- SC2 filtering ----------------
    sc2_distance_epsilon_factor: float = 1.0
    sc2_min_pair_distance: float = 1e-6
    sc2_percentile: float = 70.0
    sc2_min_keep: int = 12
    sc2_topk_ratio_fallback: float = 0.25

    # ---------------- TLS-like robust estimation ----------------
    tls_tau_factor: float = 1.5
    tls_max_iter: int = 30
    tls_tol: float = 1e-7

    # ---------------- Visualization ----------------
    visualize: bool = False
    save_transformed_source: bool = True
    transformed_source_output: str = "outputs/scanbody_match/source_registered_final.ply"


# ============================================================
# Geometry I/O
# ============================================================
MESH_EXT = {".stl", ".obj", ".off", ".ply", ".glb", ".gltf", ".fbx"}


def _extension(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def read_as_point_cloud(path: str, sample_points: int) -> o3d.geometry.PointCloud:
    ext = _extension(path)

    # 优先尝试按网格读取
    if ext in MESH_EXT:
        mesh = o3d.io.read_triangle_mesh(path)
        if mesh is not None and len(mesh.triangles) > 0:
            if not mesh.has_vertex_normals():
                mesh.compute_vertex_normals()
            pcd = mesh.sample_points_poisson_disk(
                number_of_points=sample_points,
                init_factor=5
            )
            return pcd,mesh

    # 回退到直接点云读取
    pcd = o3d.io.read_point_cloud(path)
    if pcd is not None and len(pcd.points) > 0:
        return pcd,None

    raise ValueError("Failed to read geometry from: {}".format(path))


# ============================================================
# Preprocessing
# ============================================================
def preprocess_point_cloud(
    pcd: o3d.geometry.PointCloud,
    voxel_size: float,
    nb_neighbors: int,
    std_ratio: float,
    normal_radius_factor: float,
    fpfh_radius_factor: float,
) -> Tuple[o3d.geometry.PointCloud, o3d.pipelines.registration.Feature, Dict[str, int]]:
    info = {"input_points": len(pcd.points)}

    # 统计离群点滤波
    pcd_filtered, _ = pcd.remove_statistical_outlier(
        nb_neighbors=nb_neighbors,
        std_ratio=std_ratio
    )
    info["after_sor_points"] = len(pcd_filtered.points)

    # 体素下采样
    pcd_down = pcd_filtered.voxel_down_sample(voxel_size)
    info["after_voxel_points"] = len(pcd_down.points)

    # 法向量估计
    normal_radius = normal_radius_factor * voxel_size
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=normal_radius, max_nn=30)
    )
    pcd_down.normalize_normals()

    # FPFH 特征
    fpfh_radius = fpfh_radius_factor * voxel_size
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        pcd_down,
        o3d.geometry.KDTreeSearchParamHybrid(radius=fpfh_radius, max_nn=100),
    )
    return pcd_down, fpfh, info


# ============================================================
# Coarse registration (FPFH + RANSAC)
# ============================================================
def coarse_registration_fpfh(
    source_down: o3d.geometry.PointCloud,
    target_down: o3d.geometry.PointCloud,
    source_fpfh: o3d.pipelines.registration.Feature,
    target_fpfh: o3d.pipelines.registration.Feature,
    voxel_size: float,
    distance_factor: float,
    ransac_n: int,
    max_iteration: int,
    max_validation: int,
):
    distance_threshold = distance_factor * voxel_size
    result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        source_down,
        target_down,
        source_fpfh,
        target_fpfh,
        True,
        distance_threshold,
        o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        ransac_n,
        [
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold),
        ],
        o3d.pipelines.registration.RANSACConvergenceCriteria(max_iteration, max_validation),
    )
    return result


# ============================================================
# Correspondence generation after coarse registration
# ============================================================
def nearest_neighbor_correspondences(
    source_points: np.ndarray,
    target_points: np.ndarray,
    max_distance: float,
):
    target_pcd = o3d.geometry.PointCloud()
    target_pcd.points = o3d.utility.Vector3dVector(target_points)
    kdtree = o3d.geometry.KDTreeFlann(target_pcd)

    src_idx, tgt_idx, nn_dists = [], [], []
    for i, p in enumerate(source_points):
        k, idx, dist2 = kdtree.search_knn_vector_3d(p, 1)
        if k > 0:
            d = float(np.sqrt(dist2[0]))
            if d <= max_distance:
                src_idx.append(i)
                tgt_idx.append(idx[0])
                nn_dists.append(d)

    return (
        np.asarray(src_idx, dtype=np.int64),
        np.asarray(tgt_idx, dtype=np.int64),
        np.asarray(nn_dists, dtype=np.float64),
    )


# ============================================================
# SC2 correspondence filtering
# ============================================================
def pairwise_distances(x: np.ndarray) -> np.ndarray:
    diff = x[:, None, :] - x[None, :, :]
    return np.linalg.norm(diff, axis=2)


def sc2_filter_correspondences(
    src_corr: np.ndarray,
    tgt_corr: np.ndarray,
    distance_epsilon: float,
    min_pair_distance: float,
    percentile: float,
    min_keep: int,
    topk_ratio_fallback: float,
):
    n = src_corr.shape[0]
    if n < 3:
        keep = np.ones(n, dtype=bool)
        scores = np.ones(n, dtype=np.float64)
        return keep, scores, None, None, 0

    d_src = pairwise_distances(src_corr)
    d_tgt = pairwise_distances(tgt_corr)

    valid = (d_src > min_pair_distance) & (d_tgt > min_pair_distance)
    A = (np.abs(d_src - d_tgt) < distance_epsilon) & valid
    np.fill_diagonal(A, False)

    # 二阶空间一致性矩阵
    A_int = A.astype(np.int32)
    S = A_int @ A_int
    np.fill_diagonal(S, 0)

    scores = S.sum(axis=1).astype(np.float64)
    ref = int(np.argmax(scores))

    eta = np.percentile(S[ref], percentile)
    keep = A[ref] & (S[ref] >= eta)
    keep[ref] = True

    # 共识集过小时回退
    if keep.sum() < min_keep:
        topk = max(min_keep, int(np.ceil(topk_ratio_fallback * n)))
        topk = min(topk, n)
        order = np.argsort(scores)[::-1]
        keep = np.zeros(n, dtype=bool)
        keep[order[:topk]] = True

    return keep, scores, A, S, ref


# ============================================================
# Rigid transform estimation
# ============================================================
def weighted_procrustes(src: np.ndarray, tgt: np.ndarray, weights: np.ndarray = None) -> np.ndarray:
    if src.shape[0] != tgt.shape[0] or src.shape[0] < 3:
        raise ValueError("Need at least 3 paired points with equal size.")

    if weights is None:
        weights = np.ones(src.shape[0], dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    weights = np.maximum(weights, 1e-12)
    weights = weights / np.sum(weights)

    src_centroid = np.sum(src * weights[:, None], axis=0)
    tgt_centroid = np.sum(tgt * weights[:, None], axis=0)

    src_centered = src - src_centroid
    tgt_centered = tgt - tgt_centroid

    H = (src_centered * weights[:, None]).T @ tgt_centered
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1.0
        R = Vt.T @ U.T
    t = tgt_centroid - R @ src_centroid

    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def transform_points(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    return (T[:3, :3] @ points.T).T + T[:3, 3]


# ============================================================
# TLS-like robust estimation
# ============================================================
def tls_registration(
    src_corr: np.ndarray,
    tgt_corr: np.ndarray,
    tau: float,
    max_iter: int,
    tol: float,
):
    T = weighted_procrustes(src_corr, tgt_corr)
    prev_obj = np.inf
    prev_weights = None

    history = []
    for it in range(max_iter):
        src_now = transform_points(src_corr, T)
        residuals = np.linalg.norm(src_now - tgt_corr, axis=1)

        # 截断损失思想下的权重更新
        weights = np.ones_like(residuals)
        outlier_mask = residuals > tau
        weights[outlier_mask] = tau / (residuals[outlier_mask] + 1e-12)

        if np.count_nonzero(weights > 1e-6) < 3:
            break

        T_new = weighted_procrustes(src_corr, tgt_corr, weights)
        obj = np.sum(np.minimum(residuals ** 2, tau ** 2))
        history.append((it, obj, residuals.mean(), residuals.max(), int(np.sum(residuals <= tau))))

        dT = np.linalg.norm(T_new - T)
        same_weights = prev_weights is not None and np.allclose(weights, prev_weights, atol=1e-6)

        if abs(prev_obj - obj) < tol and (dT < tol or same_weights):
            T = T_new
            prev_obj = obj
            prev_weights = weights
            break

        T = T_new
        prev_obj = obj
        prev_weights = weights

    src_final = transform_points(src_corr, T)
    residuals = np.linalg.norm(src_final - tgt_corr, axis=1)
    inlier_mask = residuals <= tau
    obj = np.sum(np.minimum(residuals ** 2, tau ** 2))

    stats = {
        "iterations": len(history),
        "objective": float(obj),
        "mean_residual": float(np.mean(residuals)) if residuals.size else np.inf,
        "rmse_residual": float(np.sqrt(np.mean(residuals ** 2))) if residuals.size else np.inf,
        "max_residual": float(np.max(residuals)) if residuals.size else np.inf,
        "num_inliers": int(np.sum(inlier_mask)),
        "num_total": int(residuals.size),
    }
    return T, inlier_mask, residuals, history, stats


# ============================================================
# Visualization
# ============================================================
def paint_and_draw(
    source: o3d.geometry.PointCloud,
    target: o3d.geometry.PointCloud,
    T: np.ndarray,
    title: str
):
    src = copy.deepcopy(source)
    tgt = copy.deepcopy(target)
    src.paint_uniform_color([1.0, 0.706, 0.0])
    tgt.paint_uniform_color([0.0, 0.651, 0.929])
    src.transform(T)
    o3d.visualization.draw_geometries([src, tgt], window_name=title)


# ============================================================
# Pipeline
# ============================================================
def _log(log_fn: Optional[Callable[[str], None]], text: str):
    if log_fn is not None:
        log_fn(text)


def run_pipeline(
    cfg: Config,
    log_fn: Optional[Callable[[str], None]] = None,
    enable_refine: bool = True,
):
    _log(log_fn, "[扫描杆匹配] 加载几何数据")
    source_raw, source_mesh = read_as_point_cloud(cfg.source_path, cfg.source_sample_points)
    target_raw, target_mesh = read_as_point_cloud(cfg.target_path, cfg.target_sample_points)

    _log(log_fn, "[扫描杆匹配] 源点云点数: {}".format(len(source_raw.points)))
    _log(log_fn, "[扫描杆匹配] 目标点云点数: {}".format(len(target_raw.points)))

    _log(log_fn, "[扫描杆匹配] 开始点云预处理")
    source_down, source_fpfh, src_info = preprocess_point_cloud(
        source_raw,
        cfg.voxel_size,
        cfg.sor_nb_neighbors,
        cfg.sor_std_ratio,
        cfg.normal_radius_factor,
        cfg.fpfh_radius_factor,
    )
    target_down, target_fpfh, tgt_info = preprocess_point_cloud(
        target_raw,
        cfg.voxel_size,
        cfg.sor_nb_neighbors,
        cfg.sor_std_ratio,
        cfg.normal_radius_factor,
        cfg.fpfh_radius_factor,
    )

    _log(log_fn, "[扫描杆匹配] 源预处理信息: {}".format(src_info))
    _log(log_fn, "[扫描杆匹配] 目标预处理信息: {}".format(tgt_info))

    _log(log_fn, "[扫描杆匹配] 执行 FPFH + RANSAC 粗配准")
    coarse = coarse_registration_fpfh(
        source_down,
        target_down,
        source_fpfh,
        target_fpfh,
        cfg.voxel_size,
        cfg.ransac_distance_factor,
        cfg.ransac_n,
        cfg.ransac_max_iteration,
        cfg.ransac_max_validation,
    )
    T0 = coarse.transformation

    _log(log_fn, "[扫描杆匹配] 粗配准 fitness: {:.6f}".format(coarse.fitness))
    _log(log_fn, "[扫描杆匹配] 粗配准 inlier_rmse: {:.6f}".format(coarse.inlier_rmse))

    source_down_coarse = copy.deepcopy(source_down)
    source_down_coarse.transform(T0)

    if cfg.visualize:
        paint_and_draw(source_down, target_down, T0, "Stage 1 - FPFH coarse registration")

    # 如果界面里选择只做粗配准
    if not enable_refine:
        T_final = T0.copy()

        if cfg.save_transformed_source:
            os.makedirs(os.path.dirname(cfg.transformed_source_output), exist_ok=True)
            src_final = copy.deepcopy(source_raw)
            src_final.transform(T_final)
            o3d.io.write_point_cloud(cfg.transformed_source_output, src_final)

        return {
            "T0": T0,
            "T1": np.eye(4, dtype=np.float64),
            "T_final": T_final,
            "src_info": src_info,
            "tgt_info": tgt_info,
            "num_corr_initial": 0,
            "num_corr_sc2": 0,
            "tls_stats": None,
            "tls_history": [],
            "sc2_keep_mask": None,
            "sc2_scores": None,
            "tls_inlier_mask": None,
            "tls_residuals": None,
            "coarse_fitness": float(coarse.fitness),
            "coarse_inlier_rmse": float(coarse.inlier_rmse),
            "transformed_source_output": cfg.transformed_source_output if cfg.save_transformed_source else None,
        }

    _log(log_fn, "[扫描杆匹配] 粗配准后建立最近邻对应")
    src_pts = np.asarray(source_down_coarse.points)
    tgt_pts = np.asarray(target_down.points)
    corr_distance = cfg.correspondence_distance_factor * cfg.voxel_size
    src_idx, tgt_idx, nn_dists = nearest_neighbor_correspondences(src_pts, tgt_pts, corr_distance)

    _log(log_fn, "[扫描杆匹配] 初始对应数: {}".format(len(src_idx)))
    if len(nn_dists) > 0:
        _log(
            log_fn,
            "[扫描杆匹配] 最近邻距离均值 / 最大值: {:.6f} / {:.6f}".format(
                float(nn_dists.mean()), float(nn_dists.max())
            )
        )

    if len(src_idx) < 3:
        raise RuntimeError(
            "粗配准后可用对应过少，请检查模型、单位尺度或适当增大对应距离阈值。"
        )

    src_corr = src_pts[src_idx]
    tgt_corr = tgt_pts[tgt_idx]

    _log(log_fn, "[扫描杆匹配] 执行 SC2 对应筛选")
    sc2_eps = cfg.sc2_distance_epsilon_factor * cfg.voxel_size
    keep_mask, scores, _, _, ref = sc2_filter_correspondences(
        src_corr,
        tgt_corr,
        distance_epsilon=sc2_eps,
        min_pair_distance=cfg.sc2_min_pair_distance,
        percentile=cfg.sc2_percentile,
        min_keep=cfg.sc2_min_keep,
        topk_ratio_fallback=cfg.sc2_topk_ratio_fallback,
    )
    src_corr_sc2 = src_corr[keep_mask]
    tgt_corr_sc2 = tgt_corr[keep_mask]

    _log(
        log_fn,
        "[扫描杆匹配] SC2 保留对应数: {} / {}".format(len(src_corr_sc2), len(src_corr))
    )
    _log(log_fn, "[扫描杆匹配] 参考对应索引: {}".format(ref))

    if len(src_corr_sc2) < 3:
        raise RuntimeError("SC2 筛选后对应不足，无法继续鲁棒变换估计。")

    _log(log_fn, "[扫描杆匹配] 执行 TLS-like 鲁棒刚体估计")
    tau = cfg.tls_tau_factor * cfg.voxel_size
    T1, tls_inlier_mask, tls_residuals, tls_history, tls_stats = tls_registration(
        src_corr_sc2,
        tgt_corr_sc2,
        tau=tau,
        max_iter=cfg.tls_max_iter,
        tol=cfg.tls_tol,
    )

    T_final = T1 @ T0
    _log(log_fn, "[扫描杆匹配] 精配准完成")
    _log(log_fn, "[扫描杆匹配] 最终残差 RMSE: {:.6f}".format(tls_stats["rmse_residual"]))

    if cfg.visualize:
        paint_and_draw(source_down_coarse, target_down, T1, "Stage 4 - TLS fine registration")
        paint_and_draw(source_down, target_down, T_final, "Final registration result")

    if cfg.save_transformed_source:
        os.makedirs(os.path.dirname(cfg.transformed_source_output), exist_ok=True)
        src_final = copy.deepcopy(source_mesh)
        src_final.transform(T_final)
        o3d.io.write_triangle_mesh(cfg.transformed_source_output, src_final)
        _log(log_fn, "[扫描杆匹配] 已保存配准后扫描杆: {}".format(cfg.transformed_source_output))

    return {
        "T0": T0,
        "T1": T1,
        "T_final": T_final,
        "src_info": src_info,
        "tgt_info": tgt_info,
        "num_corr_initial": len(src_corr),
        "num_corr_sc2": len(src_corr_sc2),
        "tls_stats": tls_stats,
        "tls_history": tls_history,
        "sc2_keep_mask": keep_mask,
        "sc2_scores": scores,
        "tls_inlier_mask": tls_inlier_mask,
        "tls_residuals": tls_residuals,
        "coarse_fitness": float(coarse.fitness),
        "coarse_inlier_rmse": float(coarse.inlier_rmse),
        "transformed_source_output": cfg.transformed_source_output if cfg.save_transformed_source else None,
    }


# ============================================================
# System wrapper
# ============================================================
class ScanbodyMatcher:
    """
    扫描杆自动匹配模块（系统封装版）
    """

    def __init__(self):
        self.name = "ScanbodyMatcher"

    def run(
        self,
        standard_scanbody_path: str,
        oral_scanbody_path: str,
        params: dict,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        try:
            cfg = self._build_config(
                standard_scanbody_path=standard_scanbody_path,
                oral_scanbody_path=oral_scanbody_path,
                params=params,
            )

            enable_refine = params.get("enable_refine", True)

            raw_result = run_pipeline(
                cfg=cfg,
                log_fn=log_callback,
                enable_refine=enable_refine,
            )

            T_final = raw_result["T_final"]
            T_inv = np.linalg.inv(T_final)

            result = {
                "module": self.name,
                "status": "success",
                "message": "扫描杆自动匹配完成",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "standard_scanbody_path": standard_scanbody_path,
                    "oral_scanbody_path": oral_scanbody_path,
                },
                "params": params,
                "output": {
                    "transformation": T_final.tolist(),
                    "inverse_transformation": T_inv.tolist(),
                    "transformation_coarse": raw_result["T0"].tolist(),
                    "transformation_refine": raw_result["T1"].tolist(),
                    "coarse_fitness": raw_result.get("coarse_fitness"),
                    "coarse_inlier_rmse": raw_result.get("coarse_inlier_rmse"),
                    "rmse": raw_result["tls_stats"]["rmse_residual"] if raw_result["tls_stats"] else raw_result.get(
                        "coarse_inlier_rmse"),
                    "fitness": raw_result.get("coarse_fitness"),
                    "num_corr_initial": raw_result["num_corr_initial"],
                    "num_corr_sc2": raw_result["num_corr_sc2"],
                    "tls_stats": raw_result["tls_stats"],
                    "src_info": raw_result["src_info"],
                    "tgt_info": raw_result["tgt_info"],
                    "aligned_model_path": raw_result.get("transformed_source_output"),
                }
            }
            return result

        except Exception as e:
            if log_callback is not None:
                log_callback("[扫描杆匹配][错误] {}".format(str(e)))

            return {
                "module": self.name,
                "status": "failed",
                "message": "扫描杆自动匹配失败: {}".format(str(e)),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "input": {
                    "standard_scanbody_path": standard_scanbody_path,
                    "oral_scanbody_path": oral_scanbody_path,
                },
                "params": params,
                "output": None,
            }

    def _build_config(
        self,
        standard_scanbody_path: str,
        oral_scanbody_path: str,
        params: dict,
    ) -> Config:
        voxel_size = float(params.get("voxel_size", 0.25))
        distance_threshold = float(params.get("distance_threshold", 1.5))

        # 当前 GUI 原有参数与算法 Config 的映射
        distance_factor = distance_threshold / voxel_size if voxel_size > 1e-12 else 1.5

        output_dir = os.path.join("outputs", "scanbody_match")
        os.makedirs(output_dir, exist_ok=True)

        cfg = Config(
            source_path=standard_scanbody_path,
            target_path=oral_scanbody_path,
            voxel_size=voxel_size,
            ransac_max_iteration=int(params.get("ransac_iterations", 4000)),
            ransac_distance_factor=distance_factor,
            correspondence_distance_factor=float(params.get("correspondence_distance_factor", distance_factor)),
            tls_tau_factor=float(params.get("tls_tau_factor", distance_factor)),
            visualize=bool(params.get("visualize", False)),
            save_transformed_source=bool(params.get("save_transformed_source", True)),
            transformed_source_output=os.path.join(output_dir, "source_registered_final.ply"),
        )

        # 如果后面你在界面里补了更细参数，这里会自动接收
        cfg.source_sample_points = int(params.get("source_sample_points", cfg.source_sample_points))
        cfg.target_sample_points = int(params.get("target_sample_points", cfg.target_sample_points))
        cfg.sor_nb_neighbors = int(params.get("sor_nb_neighbors", cfg.sor_nb_neighbors))
        cfg.sor_std_ratio = float(params.get("sor_std_ratio", cfg.sor_std_ratio))

        cfg.normal_radius_factor = float(params.get("normal_radius_factor", cfg.normal_radius_factor))
        cfg.fpfh_radius_factor = float(params.get("fpfh_radius_factor", cfg.fpfh_radius_factor))
        cfg.ransac_n = int(params.get("ransac_n", cfg.ransac_n))
        cfg.ransac_max_validation = int(params.get("ransac_max_validation", cfg.ransac_max_validation))

        cfg.sc2_distance_epsilon_factor = float(params.get("sc2_distance_epsilon_factor", cfg.sc2_distance_epsilon_factor))
        cfg.sc2_min_pair_distance = float(params.get("sc2_min_pair_distance", cfg.sc2_min_pair_distance))
        cfg.sc2_percentile = float(params.get("sc2_percentile", cfg.sc2_percentile))
        cfg.sc2_min_keep = int(params.get("sc2_min_keep", cfg.sc2_min_keep))
        cfg.sc2_topk_ratio_fallback = float(params.get("sc2_topk_ratio_fallback", cfg.sc2_topk_ratio_fallback))

        cfg.tls_max_iter = int(params.get("tls_max_iter", cfg.tls_max_iter))
        cfg.tls_tol = float(params.get("tls_tol", cfg.tls_tol))

        return cfg