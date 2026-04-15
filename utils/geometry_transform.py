# utils/geometry_transform.py
import os
from pathlib import Path

import numpy as np
import open3d as o3d


MESH_EXT = {".stl", ".obj", ".off", ".ply", ".glb", ".gltf", ".fbx"}
PCD_EXT = {".pcd", ".ply", ".xyz", ".xyzn", ".xyzrgb", ".pts"}


def _ext(path: str) -> str:
    return Path(path).suffix.lower()


def transform_txt_data(input_path: str, output_path: str, matrix: np.ndarray) -> str:
    data = np.loadtxt(input_path)
    if data.ndim == 1:
        data = data.reshape(1, -1)

    if data.shape[1] < 3:
        raise ValueError("TXT 数据至少需要前三列为 xyz 坐标。")

    R = matrix[:3, :3]
    t = matrix[:3, 3]

    # 变换 xyz
    xyz = data[:, :3]
    xyz_new = (R @ xyz.T).T + t
    data[:, :3] = xyz_new

    # 如果有法向量，则只做旋转
    if data.shape[1] >= 6:
        normals = data[:, 3:6]
        normals_new = (R @ normals.T).T
        data[:, 3:6] = normals_new

    np.savetxt(output_path, data, fmt="%.8f")
    return output_path


def transform_geometry_file(input_path: str, output_path: str, matrix: np.ndarray) -> str:
    ext = _ext(input_path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    if ext == ".txt":
        return transform_txt_data(input_path, output_path, matrix)

    if ext in MESH_EXT:
        mesh = o3d.io.read_triangle_mesh(input_path)
        if mesh is not None and len(mesh.vertices) > 0 and len(mesh.triangles) > 0:
            if not mesh.has_vertex_normals():
                mesh.compute_vertex_normals()
            mesh.transform(matrix)
            ok = o3d.io.write_triangle_mesh(output_path, mesh)
            if not ok:
                raise RuntimeError("网格写出失败: {}".format(output_path))
            return output_path

    pcd = o3d.io.read_point_cloud(input_path)
    if pcd is not None and len(pcd.points) > 0:
        pcd.transform(matrix)
        ok = o3d.io.write_point_cloud(output_path, pcd)
        if not ok:
            raise RuntimeError("点云写出失败: {}".format(output_path))
        return output_path

    raise ValueError("无法读取并变换模型文件: {}".format(input_path))