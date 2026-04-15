# widgets/viewer_panel.py
import os
from pathlib import Path

import vtk
import numpy as np
import open3d as o3d
import pyvista as pv
from pyvistaqt import QtInteractor

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QFrame,
    QMessageBox,
    QFileDialog,
)


MESH_EXT = {".stl", ".obj", ".off", ".ply", ".glb", ".gltf", ".fbx"}


class ViewerPanel(QWidget):
    """
    PyVistaQt 内嵌三维显示区
    - 算法继续使用 Open3D
    - 界面显示使用 PyVistaQt
    """

    DISPLAY_NAME_MAP = {
        "standard_scanbody": "标准扫描杆",
        "standard_abutment": "标准基台",
        "oral_scanbody": "患者扫描杆",
        "gingiva_mesh": "完整模型",
        "cuff_data": "袖口数据",
        "match_result": "扫描杆匹配结果",
        "cuff_result": "袖口边缘顶点",
        "abutment_result": "基台生成结果",

        "oral_scanbody_in_standard": "变换后患者扫描杆",
        "cuff_data_in_standard": "变换后袖口",
        "gingiva_mesh_in_standard": "变换后完整模型",
    }

    COLOR_MAP = {
        "standard_scanbody": [1.0, 0.706, 0.0],
        "standard_abutment": [0.82, 0.82, 0.82],
        "oral_scanbody": [0.0, 0.651, 0.929],
        "gingiva_mesh": [0.78, 0.78, 0.78],
        "cuff_data": [0.95, 0.2, 0.2],
        "match_result": [0.2, 0.75, 0.2],
        "cuff_result": [0.85, 0.2, 0.75],
        "abutment_result": [0.3, 0.8, 0.8],

        "oral_scanbody_in_standard": [0.2, 0.75, 0.2],
        "cuff_data_in_standard": [0.85, 0.2, 0.75],
        "gingiva_mesh_in_standard": [0.55, 0.55, 0.55],
    }

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scene_objects = {}
        self.model_items = {}
        self.model_visibility = {}
        self.axes_enabled = True

        self._init_ui()
        self._init_plotter()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._build_toolbar())
        root_layout.addWidget(self._build_viewport_group(), 5)
        root_layout.addWidget(self._build_scene_info_group(), 2)

    def _build_toolbar(self):
        container = QFrame()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.btn_reset_view = QPushButton("重置视图")
        self.btn_toggle_axes = QPushButton("隐藏坐标轴")
        self.btn_export_screenshot = QPushButton("导出截图")
        self.btn_clear_scene = QPushButton("清空显示")
        self.btn_refresh_info = QPushButton("刷新状态")

        self.btn_reset_view.clicked.connect(self.reset_view)
        self.btn_toggle_axes.clicked.connect(self.toggle_axes)
        self.btn_export_screenshot.clicked.connect(self.export_screenshot)
        self.btn_clear_scene.clicked.connect(self.clear_scene)
        self.btn_refresh_info.clicked.connect(self.refresh_scene_info)

        layout.addWidget(self.btn_reset_view)
        layout.addWidget(self.btn_toggle_axes)
        layout.addWidget(self.btn_export_screenshot)
        layout.addWidget(self.btn_clear_scene)
        layout.addWidget(self.btn_refresh_info)
        layout.addStretch(1)

        return container

    def _build_viewport_group(self):
        group = QGroupBox("三维显示区")
        layout = QVBoxLayout(group)

        self.viewport_frame = QFrame()
        self.viewport_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #bfbfbf;
                background: #ffffff;
            }
        """)
        self.viewport_layout = QVBoxLayout(self.viewport_frame)
        self.viewport_layout.setContentsMargins(0, 0, 0, 0)
        self.viewport_layout.setSpacing(0)

        layout.addWidget(self.viewport_frame)
        return group

    def _build_scene_info_group(self):
        group = QGroupBox("场景信息")
        layout = QHBoxLayout(group)
        layout.setSpacing(8)

        self.model_list = QListWidget()

        self.result_summary = QTextEdit()
        self.result_summary.setReadOnly(True)
        self.result_summary.setPlaceholderText("算法结果摘要将在此显示。")

        layout.addWidget(self.model_list, 2)
        layout.addWidget(self.result_summary, 3)
        return group

    def _init_plotter(self):
        self.plotter = QtInteractor(self.viewport_frame)
        self.viewport_layout.addWidget(self.plotter.interactor)

        self.plotter.set_background("white")
        self.plotter.add_axes()
        self.plotter.enable_parallel_projection()
        self.plotter.show_grid(color="lightgray")
        self.plotter.camera_position = "iso"
        self.plotter.reset_camera()

    # ============================================================
    # 外部接口
    # ============================================================
    def load_model(self, key: str, file_path: str, display_name: str = None):
        pv_data, render_style, has_rgb = self._read_geometry_as_pyvista(file_path, key)

        if key in self.scene_objects:
            self._remove_actor(key)

        actor = self._add_pyvista_object(
            key=key,
            pv_data=pv_data,
            render_style=render_style,
            has_rgb=has_rgb,
        )

        obj = {
            "key": key,
            "path": file_path,
            "name": display_name or self.DISPLAY_NAME_MAP.get(key, key),
            "pv_data": pv_data,
            "actor": actor,
            "visible": True,
            "render_style": render_style,
            "has_rgb": has_rgb,
        }

        self.scene_objects[key] = obj
        self.model_visibility[key] = True
        self._update_scene_item(key)
        self._append_result_text(
            "[显示] 已加载模型：{} -> {}".format(obj["name"], Path(file_path).name)
        )
        self.plotter.reset_camera()
        self.plotter.render()

    def load_placeholder_model(self, key: str, file_path: str):
        # 兼容你之前 main_window 里的旧调用
        self.load_model(key, file_path)

    def show_algorithm_result(self, result_key: str, result, display_type: str = None):
        self._append_result_text(self._format_result_text(result_key, result, display_type))

        if not isinstance(result, dict):
            return

        if result.get("status") != "success":
            return

        output = result.get("output", {})
        if not isinstance(output, dict):
            return

        if result_key == "match_result":
            aligned_path = output.get("aligned_model_path")
            if aligned_path and os.path.exists(aligned_path):
                self.load_model("match_result", aligned_path, display_name="扫描杆匹配结果")


        elif result_key == "cuff_result":

            actual_display_type = display_type or result.get("params", {}).get("display_result_type",
                                                                               "reference_boundary")
            self.update_cuff_result_display(result, actual_display_type)

        elif result_key == "abutment_result":
            model_path = output.get("output_model_path")
            if model_path and os.path.exists(model_path):
                self.load_model("abutment_result", model_path, display_name="基台生成结果")

    def toggle_model_visibility(self, key: str):
        if key not in self.scene_objects:
            self._append_result_text("[显示] 未找到场景对象：{}".format(key))
            return

        visible = self.model_visibility.get(key, True)
        visible = not visible
        self.model_visibility[key] = visible
        self.scene_objects[key]["visible"] = visible

        actor = self.scene_objects[key].get("actor")
        if actor is not None:
            actor.SetVisibility(1 if visible else 0)

        self._update_scene_item(key)
        self._append_result_text(
            "[显示] {} -> {}".format(
                self.scene_objects[key]["name"],
                "显示" if visible else "隐藏"
            )
        )
        self.plotter.render()

    def clear_scene(self):
        keys = list(self.scene_objects.keys())
        for key in keys:
            self._remove_actor(key)

        self.scene_objects = {}
        self.model_items = {}
        self.model_visibility = {}
        self.model_list.clear()
        self.result_summary.clear()

        self.plotter.clear()
        self.plotter.set_background("white")
        if self.axes_enabled:
            self.plotter.add_axes()
        self.plotter.show_grid(color="lightgray")
        self.plotter.camera_position = "iso"
        self.plotter.reset_camera()
        self.plotter.render()

        self._append_result_text("[显示] 场景显示信息已清空")

    def refresh_scene_info(self):
        total_models = len(self.scene_objects)
        visible_count = sum(1 for obj in self.scene_objects.values() if obj["visible"])
        hidden_count = total_models - visible_count

        text = (
            "[场景状态]\n"
            "模型总数：{}\n"
            "当前显示：{}\n"
            "当前隐藏：{}\n"
        ).format(total_models, visible_count, hidden_count)

        self._append_result_text(text)

    def reset_view(self):
        try:
            self.plotter.camera_position = "iso"
            self.plotter.reset_camera()
            self.plotter.render()
            self._append_result_text("[视图] 已重置视图")
        except Exception as e:
            self._append_result_text("[视图][错误] 重置视图失败：{}".format(str(e)))

    def toggle_axes(self):
        self.axes_enabled = not self.axes_enabled

        # 重新刷新一遍整个场景，保证坐标轴状态一致
        current_objects = list(self.scene_objects.items())

        self.plotter.clear()
        self.plotter.set_background("white")

        if self.axes_enabled:
            self.plotter.add_axes()
            self.btn_toggle_axes.setText("隐藏坐标轴")
        else:
            self.btn_toggle_axes.setText("显示坐标轴")

        self.plotter.show_grid(color="lightgray")

        for key, obj in current_objects:
            actor = self._add_pyvista_object(
                key=key,
                pv_data=obj["pv_data"],
                render_style=obj["render_style"],
                has_rgb=obj["has_rgb"],
            )
            obj["actor"] = actor
            actor.SetVisibility(1 if obj["visible"] else 0)
            self.scene_objects[key] = obj

        self.plotter.reset_camera()
        self.plotter.render()

    def export_screenshot(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出三维视图截图",
            str(Path.home() / "viewer_screenshot.png"),
            "PNG Files (*.png);;JPG Files (*.jpg *.jpeg)"
        )
        if not save_path:
            return

        try:
            self.plotter.screenshot(save_path)
            self._append_result_text("[导出] 视图截图已保存：{}".format(save_path))
        except Exception as e:
            QMessageBox.warning(self, "导出失败", "截图导出失败：\n{}".format(str(e)))

    def show_transformed_existing_object(
            self,
            source_key: str,
            result_key: str,
            matrix,
            display_name: str = None,
    ):
        """
        从当前场景中复制一个已有对象，对其施加刚体变换后作为新对象显示。
        用于：
        - 患者扫描杆 -> 变换后的患者扫描杆
        - 袖口 -> 变换后的袖口
        - 完整模型 -> 变换后的完整模型
        """
        if source_key not in self.scene_objects:
            self._append_result_text("[显示] 未找到源对象：{}".format(source_key))
            return

        source_obj = self.scene_objects[source_key]
        pv_data = source_obj["pv_data"].copy()

        mat = np.asarray(matrix, dtype=float)
        pv_data.transform(mat)

        if result_key in self.scene_objects:
            self._remove_actor(result_key)

        actor = self._add_pyvista_object(
            key=result_key,
            pv_data=pv_data,
            render_style=source_obj["render_style"],
            has_rgb=source_obj["has_rgb"],
        )

        new_obj = {
            "key": result_key,
            "path": None,
            "name": display_name or self.DISPLAY_NAME_MAP.get(result_key, result_key),
            "pv_data": pv_data,
            "actor": actor,
            "visible": True,
            "render_style": source_obj["render_style"],
            "has_rgb": source_obj["has_rgb"],
        }

        self.scene_objects[result_key] = new_obj
        self.model_visibility[result_key] = True
        self._update_scene_item(result_key)
        self.plotter.render()

        self._append_result_text(
            "[显示] 已生成变换对象：{} <- {}".format(
                new_obj["name"], source_obj["name"]
            )
        )

    def set_model_visibility(self, key: str, visible: bool):
        if key not in self.scene_objects:
            return

        self.model_visibility[key] = visible
        self.scene_objects[key]["visible"] = visible

        actor = self.scene_objects[key].get("actor")
        if actor is not None:
            actor.SetVisibility(1 if visible else 0)

        self._update_scene_item(key)
        self.plotter.render()

    def show_transformed_existing_object_shared_data(
            self,
            source_key: str,
            result_key: str,
            matrix,
            display_name: str = None,
    ):
        if source_key not in self.scene_objects:
            self._append_result_text("[显示] 未找到源对象：{}".format(source_key))
            return

        source_obj = self.scene_objects[source_key]
        pv_data = source_obj["pv_data"]  # 注意：这里不 copy，共享底层数据

        if result_key in self.scene_objects:
            self._remove_actor(result_key)

        actor = self._add_pyvista_object(
            key=result_key,
            pv_data=pv_data,
            render_style=source_obj["render_style"],
            has_rgb=source_obj["has_rgb"],
        )

        vtk_mat = self._numpy_to_vtk_matrix(matrix)
        actor.SetUserMatrix(vtk_mat)

        new_obj = {
            "key": result_key,
            "path": None,
            "name": display_name or self.DISPLAY_NAME_MAP.get(result_key, result_key),
            "pv_data": pv_data,  # 共享同一份底层几何
            "actor": actor,
            "visible": True,
            "render_style": source_obj["render_style"],
            "has_rgb": source_obj["has_rgb"],
            "actor_transform": np.asarray(matrix, dtype=float),
        }

        self.scene_objects[result_key] = new_obj
        self.model_visibility[result_key] = True
        self._update_scene_item(result_key)
        self.plotter.render()

        self._append_result_text(
            "[显示] 已生成变换对象（共享底层数据）：{} <- {}".format(
                new_obj["name"], source_obj["name"]
            )
        )

    def update_cuff_result_display(self, result: dict, display_type: str = "reference_boundary"):
        if not isinstance(result, dict):
            return

        if result.get("status") != "success":
            return

        output = result.get("output", {})
        if not isinstance(output, dict):
            return

        if display_type == "raw_boundary":
            candidate = output.get("boundary_display_path")
            display_name = "原始边界"
        else:
            candidate = output.get("reference_display_path")
            display_name = "参考边界"

        if candidate and os.path.exists(candidate):
            self.load_model("cuff_result", candidate, display_name=display_name)

    # ============================================================
    # 内部逻辑
    # ============================================================
    def _read_geometry_as_pyvista(self, file_path: str, key: str):
        ext = Path(file_path).suffix.lower()

        if ext == ".txt":
            poly = self._read_txt_as_polydata(file_path, key)
            has_rgb = "rgb_colors" in poly.array_names
            return poly, "points", has_rgb

        # 优先按网格读取
        if ext in MESH_EXT:
            mesh = o3d.io.read_triangle_mesh(file_path)
            if mesh is not None and len(mesh.triangles) > 0:
                pv_mesh = self._o3d_mesh_to_pyvista(mesh)
                has_rgb = "rgb_colors" in pv_mesh.array_names
                return pv_mesh, "surface", has_rgb

        # 回退到点云读取
        pcd = o3d.io.read_point_cloud(file_path)
        if pcd is not None and len(pcd.points) > 0:
            pv_cloud = self._o3d_point_cloud_to_pyvista(pcd)
            has_rgb = "rgb_colors" in pv_cloud.array_names
            return pv_cloud, "points", has_rgb

        raise ValueError("无法读取模型文件：{}".format(file_path))

    def _read_txt_as_polydata(self, file_path: str, key: str):
        data = np.loadtxt(file_path)
        if data.ndim == 1:
            data = data.reshape(1, -1)

        if data.shape[1] < 3:
            raise ValueError("TXT 数据至少需要前三列为 xyz 坐标。")

        points = data[:, :3]
        poly = pv.PolyData(points)

        # 若最后一列是标签，则按标签着色
        if data.shape[1] >= 7:
            labels = data[:, -1]
            colors = np.zeros((points.shape[0], 3), dtype=np.uint8)
            colors[:, :] = np.array([180, 180, 180], dtype=np.uint8)
            colors[labels > 0.5] = np.array([255, 60, 60], dtype=np.uint8)
            poly["rgb_colors"] = colors
        else:
            color = np.array(self.COLOR_MAP.get(key, [0.6, 0.6, 0.6]), dtype=np.float64)
            colors = np.tile((color * 255).astype(np.uint8), (points.shape[0], 1))
            poly["rgb_colors"] = colors

        return poly

    def _o3d_point_cloud_to_pyvista(self, pcd: o3d.geometry.PointCloud):
        points = np.asarray(pcd.points)
        poly = pv.PolyData(points)

        if pcd.has_colors():
            colors = (np.asarray(pcd.colors) * 255.0).clip(0, 255).astype(np.uint8)
            poly["rgb_colors"] = colors

        return poly

    def _o3d_mesh_to_pyvista(self, mesh: o3d.geometry.TriangleMesh):
        vertices = np.asarray(mesh.vertices)
        triangles = np.asarray(mesh.triangles)

        faces = np.hstack([
            np.full((triangles.shape[0], 1), 3, dtype=np.int64),
            triangles.astype(np.int64)
        ]).ravel()

        pv_mesh = pv.PolyData(vertices, faces)

        if mesh.has_vertex_colors():
            colors = (np.asarray(mesh.vertex_colors) * 255.0).clip(0, 255).astype(np.uint8)
            pv_mesh["rgb_colors"] = colors

        return pv_mesh

    def _add_pyvista_object(self, key: str, pv_data, render_style: str, has_rgb: bool):
        base_color = self.COLOR_MAP.get(key, [0.6, 0.6, 0.6])

        if render_style == "points":
            actor = self.plotter.add_mesh(
                pv_data,
                name=key,
                color=None if has_rgb else base_color,
                scalars="rgb_colors" if has_rgb else None,
                rgb=has_rgb,
                style="points",
                point_size=8,
                render_points_as_spheres=True,
                reset_camera=False,
            )
        else:
            actor = self.plotter.add_mesh(
                pv_data,
                name=key,
                color=None if has_rgb else base_color,
                scalars="rgb_colors" if has_rgb else None,
                rgb=has_rgb,
                smooth_shading=True,
                show_edges=False,
                opacity=1.0,
                reset_camera=False,
            )

        return actor

    def _remove_actor(self, key: str):
        obj = self.scene_objects.get(key)
        if obj is None:
            return

        try:
            self.plotter.remove_actor(obj.get("actor"), render=False)
        except Exception:
            pass

    def _update_scene_item(self, key: str):
        obj = self.scene_objects.get(key)
        if obj is None:
            return

        visible = self.model_visibility.get(key, True)
        state_text = "显示" if visible else "隐藏"
        file_name = Path(obj["path"]).name if obj.get("path") else "内存对象"
        text = "{} | {} | {}".format(obj["name"], state_text, file_name)

        if key in self.model_items:
            self.model_items[key].setText(text)
        else:
            item = QListWidgetItem(text)
            self.model_list.addItem(item)
            self.model_items[key] = item

    def _format_result_text(self, result_key: str, result, display_type: str = None):
        lines = []
        lines.append("[结果] {}".format(self.DISPLAY_NAME_MAP.get(result_key, result_key)))

        if not isinstance(result, dict):
            lines.append(str(result))
            return "\n".join(lines)

        lines.append("状态：{}".format(result.get("status", "unknown")))
        lines.append("信息：{}".format(result.get("message", "")))

        output = result.get("output", {})
        if isinstance(output, dict):
            if result_key == "match_result":
                lines.append("配准后模型：{}".format(output.get("aligned_model_path")))
                lines.append("粗配准 fitness：{}".format(output.get("coarse_fitness")))
                lines.append("最终 RMSE：{}".format(output.get("rmse")))
                lines.append("初始对应数：{}".format(output.get("num_corr_initial")))
                lines.append("SC2 保留对应数：{}".format(output.get("num_corr_sc2")))



            elif result_key == "cuff_result":

                actual_display_type = display_type or result.get("params", {}).get("display_result_type",
                                                                                   "reference_boundary")
                display_name = "原始边界" if actual_display_type == "raw_boundary" else "参考边界"
                display_path = (
                    output.get("boundary_display_path")
                    if actual_display_type == "raw_boundary"
                    else output.get("reference_display_path")
                )
                lines.append("边界环数量：{}".format(output.get("loop_count")))
                lines.append("选中边界环编号：{}".format(output.get("selected_loop_id")))
                lines.append("原始边界点数量：{}".format(output.get("boundary_point_count")))
                lines.append("参考边界点数量：{}".format(output.get("reference_point_count")))
                lines.append("当前显示类型：{}".format(display_name))
                lines.append("界面显示文件：{}".format(display_path))
                lines.append("参考边界文件：{}".format(output.get("reference_curve_path")))

            elif result_key == "abutment_result":
                lines.append("输出模型：{}".format(output.get("output_model_path")))
                lines.append("ROI 顶点数：{}".format(output.get("roi_vertex_count")))
                lines.append("控制点数：{}".format(output.get("control_point_count")))

        return "\n".join(lines)

    def _append_result_text(self, text: str):
        if self.result_summary.toPlainText():
            self.result_summary.append(text)
        else:
            self.result_summary.setPlainText(text)

    def _numpy_to_vtk_matrix(self, matrix):
        mat = np.asarray(matrix, dtype=float)
        vtk_mat = vtk.vtkMatrix4x4()
        for i in range(4):
            for j in range(4):
                vtk_mat.SetElement(i, j, float(mat[i, j]))
        return vtk_mat