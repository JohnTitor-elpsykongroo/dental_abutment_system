# ui/main_window.py
import os

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QSplitter,
    QFileDialog,
    QMessageBox,
    QLabel,
    QStatusBar,
)

from widgets.data_panel import DataPanel
from widgets.viewer_panel import ViewerPanel
from widgets.control_panel import ControlPanel
from widgets.log_panel import LogPanel

from modules.scanbody_matcher import ScanbodyMatcher
from modules.cuff_segmenter import CuffSegmenter
from modules.abutment_designer import AbutmentDesigner
from modules.export_manager import ExportManager
from modules.workflow_controller import DentalDesignWorkflow

from utils.app_config import INTERNAL_CUFF_MODEL_PATH

class MainWindow(QMainWindow):
    """
    主窗口：
    - 左侧：数据管理 + 功能流程
    - 中间：三维显示区（先占位）
    - 右侧：参数设置 + 日志输出
    - 顶部：菜单栏 / 工具入口
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("个性化基台智能设计系统原型")
        self.resize(1600, 900)

        # 数据状态缓存：后续算法模块从这里取输入
        # 初始化算法模块
        self.scanbody_matcher = ScanbodyMatcher()
        self.cuff_segmenter = CuffSegmenter()
        self.abutment_designer = AbutmentDesigner()
        self.export_manager = ExportManager()
        self.workflow = DentalDesignWorkflow(
            scanbody_matcher=self.scanbody_matcher,
            cuff_segmenter=self.cuff_segmenter,
            abutment_designer=self.abutment_designer,
            export_manager=self.export_manager,
        )
        self.case_data = self.workflow.create_case_data()

        self._init_ui()
        self._init_menu()
        self._init_status_bar()
        self._connect_signals()
        self._load_internal_cuff_model()

    # =========================
    # UI 初始化
    # =========================
    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(6, 6, 6, 6)
        root_layout.setSpacing(6)

        self.main_splitter = QSplitter(Qt.Horizontal)

        # 左侧：数据与流程
        self.data_panel = DataPanel()

        # 中间：三维显示
        self.viewer_panel = ViewerPanel()

        # 右侧：参数 + 日志
        self.control_panel = ControlPanel()
        self.log_panel = LogPanel()

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)
        right_layout.addWidget(self.control_panel, 2)
        right_layout.addWidget(self.log_panel, 3)

        self.main_splitter.addWidget(self.data_panel)
        self.main_splitter.addWidget(self.viewer_panel)
        self.main_splitter.addWidget(right_container)

        # 左中右比例
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 6)
        self.main_splitter.setStretchFactor(2, 3)
        self.main_splitter.setSizes([280, 850, 420])

        self.data_panel.set_visibility_state("oral_scanbody_in_standard", False)
        self.data_panel.set_visibility_state("gingiva_mesh_in_standard", False)

        self.data_panel.set_checkbox_enabled("oral_scanbody_in_standard", False)
        self.data_panel.set_checkbox_enabled("gingiva_mesh_in_standard", False)

        root_layout.addWidget(self.main_splitter)

    def _init_menu(self):
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        action_import_std_scanbody = QAction("导入标准扫描杆模型", self)
        action_import_std_abutment = QAction("导入标准基台模型", self)
        action_import_roi_json = QAction("导入ROI索引文件", self)
        action_import_oral_scanbody = QAction("导入口扫扫描杆模型", self)
        action_import_gingiva = QAction("导入完整牙龈模型", self)
        action_import_cuff = QAction("导入袖口相关数据", self)
        action_export_result = QAction("导出结果", self)
        action_exit = QAction("退出", self)

        file_menu.addAction(action_import_std_scanbody)
        file_menu.addAction(action_import_std_abutment)
        file_menu.addAction(action_import_roi_json)
        file_menu.addAction(action_import_oral_scanbody)
        file_menu.addAction(action_import_gingiva)
        file_menu.addAction(action_import_cuff)
        file_menu.addSeparator()
        file_menu.addAction(action_export_result)
        file_menu.addSeparator()
        file_menu.addAction(action_exit)

        # 处理菜单
        process_menu = menu_bar.addMenu("处理")
        action_match = QAction("执行扫描杆匹配", self)
        action_cuff = QAction("执行袖口识别/边界定位", self)
        action_design = QAction("执行基台形态生成", self)

        process_menu.addAction(action_match)
        process_menu.addAction(action_cuff)
        process_menu.addAction(action_design)

        # 显示菜单
        view_menu = menu_bar.addMenu("显示")
        action_toggle_std_scanbody = QAction("显示/隐藏标准扫描杆", self)
        action_toggle_std_abutment = QAction("显示/隐藏标准基台", self)
        action_toggle_oral_scanbody = QAction("显示/隐藏口扫扫描杆", self)
        action_toggle_gingiva = QAction("显示/隐藏牙龈模型", self)
        action_toggle_cuff = QAction("显示/隐藏袖口数据", self)
        action_toggle_result = QAction("显示/隐藏结果模型", self)

        view_menu.addAction(action_toggle_std_scanbody)
        view_menu.addAction(action_toggle_std_abutment)
        view_menu.addAction(action_toggle_oral_scanbody)
        view_menu.addAction(action_toggle_gingiva)
        view_menu.addAction(action_toggle_cuff)
        view_menu.addAction(action_toggle_result)

        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")
        action_about = QAction("关于系统", self)
        help_menu.addAction(action_about)

        # 存为成员，便于后续扩展
        self.menu_actions = {
            "import_std_scanbody": action_import_std_scanbody,
            "import_std_abutment": action_import_std_abutment,
            "import_roi_json": action_import_roi_json,
            "import_oral_scanbody": action_import_oral_scanbody,
            "import_gingiva": action_import_gingiva,
            "export_result": action_export_result,
            "exit": action_exit,
            "match": action_match,
            "cuff": action_cuff,
            "design": action_design,
            "toggle_std_scanbody": action_toggle_std_scanbody,
            "toggle_std_abutment": action_toggle_std_abutment,
            "toggle_oral_scanbody": action_toggle_oral_scanbody,
            "toggle_gingiva": action_toggle_gingiva,
            "toggle_result": action_toggle_result,
            "about": action_about,
        }

    def _init_status_bar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_label = QLabel("系统就绪")
        status_bar.addPermanentWidget(self.status_label)

    def _connect_signals(self):
        # ===== 菜单栏 =====
        self.menu_actions["import_std_scanbody"].triggered.connect(
            lambda: self.import_model("standard_scanbody", "导入标准扫描杆模型")
        )
        self.menu_actions["import_std_abutment"].triggered.connect(
            lambda: self.import_model("standard_abutment", "导入标准基台模型")
        )

        self.menu_actions["import_roi_json"].triggered.connect(
            lambda: self.import_model("roi_indices_json", "导入 ROI 索引文件")
        )

        self.menu_actions["import_oral_scanbody"].triggered.connect(
            lambda: self.import_model("oral_scanbody", "导入口扫扫描杆模型")
        )
        self.menu_actions["import_gingiva"].triggered.connect(
            lambda: self.import_model("gingiva_mesh", "导入完整牙龈模型")
        )
        self.menu_actions["export_result"].triggered.connect(self.export_result_model)
        self.menu_actions["exit"].triggered.connect(self.close)

        self.menu_actions["match"].triggered.connect(self.run_scanbody_matching)
        self.menu_actions["cuff"].triggered.connect(self.run_cuff_segmentation)
        self.menu_actions["design"].triggered.connect(self.run_abutment_design)

        self.menu_actions["toggle_std_scanbody"].triggered.connect(
            lambda: self.toggle_model_visibility("standard_scanbody")
        )
        self.menu_actions["toggle_std_abutment"].triggered.connect(
            lambda: self.toggle_model_visibility("standard_abutment")
        )
        self.menu_actions["toggle_oral_scanbody"].triggered.connect(
            lambda: self.toggle_model_visibility("oral_scanbody")
        )
        self.menu_actions["toggle_gingiva"].triggered.connect(
            lambda: self.toggle_model_visibility("gingiva_mesh")
        )
        self.menu_actions["toggle_result"].triggered.connect(
            lambda: self.toggle_model_visibility("abutment_result")
        )
        self.menu_actions["about"].triggered.connect(self.show_about_dialog)

        # ===== 左侧数据面板 =====
        self.data_panel.import_standard_scanbody_requested.connect(
            lambda: self.import_model("standard_scanbody", "导入标准扫描杆模型")
        )
        self.data_panel.import_standard_abutment_requested.connect(
            lambda: self.import_model("standard_abutment", "导入标准基台模型")
        )
        self.data_panel.import_roi_json_requested.connect(
            lambda: self.import_model("roi_indices_json", "导入 ROI 索引文件")
        )
        self.data_panel.import_oral_scanbody_requested.connect(
            lambda: self.import_model("oral_scanbody", "导入口扫扫描杆模型")
        )
        self.data_panel.import_gingiva_requested.connect(
            lambda: self.import_model("gingiva_mesh", "导入完整牙龈模型")
        )

        self.data_panel.run_matching_requested.connect(self.run_scanbody_matching)
        self.data_panel.run_cuff_requested.connect(self.run_cuff_segmentation)
        self.data_panel.run_design_requested.connect(self.run_abutment_design)
        self.data_panel.export_requested.connect(self.export_result_model)

        self.data_panel.toggle_visibility_requested.connect(self.toggle_model_visibility)
        self.data_panel.cuff_display_type_changed.connect(self.on_cuff_display_type_changed)

    def _load_internal_cuff_model(self):
        cuff_path = str(INTERNAL_CUFF_MODEL_PATH)

        if self.workflow.load_internal_cuff(self.case_data, cuff_path):
            self.append_log("[内部数据] 已加载袖口模型: {}".format(cuff_path))
        else:
            self.append_log("[警告] 内部袖口模型不存在: {}".format(cuff_path))

    def sync_model_visibility(self, key: str, visible: bool):
        """
        同步三维场景显示状态 + 左侧复选框状态
        """
        self.viewer_panel.set_model_visibility(key, visible)
        self.data_panel.set_visibility_state(key, visible)
    # =========================
    # 文件导入
    # =========================
    @Slot()
    def import_model(self, key: str, title: str):
        if key == "roi_indices_json":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                title,
                "",
                "JSON Files (*.json);;All Files (*)"
            )
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                title,
                "",
                "3D Files (*.ply *.stl *.obj *.off *.pcd *.txt);;All Files (*)"
            )

        if not file_path:
            return

        updates = self.workflow.register_import(
            case_data=self.case_data,
            key=key,
            file_path=file_path,
        )

        if updates.get("reset_transformed_views"):
            self.viewer_panel.set_model_visibility("oral_scanbody_in_standard", False)
            self.data_panel.set_visibility_state("oral_scanbody_in_standard", False)
            self.data_panel.set_checkbox_enabled("oral_scanbody_in_standard", False)

        self.data_panel.update_file_status(key, file_path)

        # 只有 3D 模型才进 viewer
        if key != "roi_indices_json":
            self.viewer_panel.load_model(key, file_path)

        self.append_log("[导入] {}: {}".format(title, file_path))
        self.set_status("{}完成".format(title))


    # =========================
    # 功能流程：扫描杆匹配
    # =========================
    @Slot()
    def run_scanbody_matching(self):
        validation_error = self.workflow.validate_before_match(self.case_data)
        if validation_error:
            QMessageBox.warning(self, "输入不完整", validation_error)
            return

        params = self.control_panel.get_scanbody_match_params()
        self.append_log("[处理] 开始执行扫描杆自动匹配...")
        self.append_log(f"[参数] 匹配参数: {params}")
        self.set_status("正在执行扫描杆匹配")

        workflow_result = self.workflow.run_scanbody_matching(
            case_data=self.case_data,
            params=params,
            log_callback=self.append_log,
        )
        result = workflow_result["result"]
        transformed_outputs = workflow_result["transformed_outputs"]

        if result.get("status") == "success":
            self.append_log("[完成] 扫描杆匹配完成")

            T_inv = result.get("output", {}).get("inverse_transformation")
            self.append_log("[结果] 最终变换矩阵: {}".format(result["output"]["transformation"]))
            self.append_log("[结果] 逆变换矩阵: {}".format(T_inv))

            oral_out = transformed_outputs.get("oral_scanbody_in_standard")
            if oral_out:
                self.viewer_panel.load_model(
                    "oral_scanbody_in_standard",
                    oral_out,
                    display_name="变换后患者扫描杆"
                )
                self.data_panel.set_checkbox_enabled("oral_scanbody_in_standard", True)
                self.data_panel.set_visibility_state("oral_scanbody_in_standard", True)
                self.sync_model_visibility("oral_scanbody", False)

            gingiva_out = transformed_outputs.get("gingiva_mesh_in_standard")
            if gingiva_out:
                self.viewer_panel.load_model(
                    "gingiva_mesh_in_standard",
                    gingiva_out,
                    display_name="变换后患者牙齿模型"
                )
                self.data_panel.set_checkbox_enabled("gingiva_mesh_in_standard", True)
                self.data_panel.set_visibility_state("gingiva_mesh_in_standard", True)
                self.sync_model_visibility("gingiva_mesh", False)

            cuff_out = transformed_outputs.get("cuff_data_in_standard")
            if cuff_out:
                self.append_log("[内部数据] 袖口模型已完成坐标变换: {}".format(cuff_out))

            self.set_status("扫描杆匹配完成")
        else:
            self.append_log("[失败] {}".format(result.get("message")))
            self.set_status("扫描杆匹配失败")

    # =========================
    # 功能流程：袖口识别 / 边界定位
    # =========================
    @Slot()
    def run_cuff_segmentation(self):
        validation_error = self.workflow.validate_before_cuff(self.case_data)
        if validation_error:
            QMessageBox.warning(self, "流程未完成", validation_error)
            return

        params = self.control_panel.get_cuff_params()
        self.append_log("[处理] 开始执行袖口识别/边界定位...")
        self.append_log("[参数] 袖口参数: {}".format(params))
        self.set_status("正在执行袖口识别/边界定位")

        result = self.workflow.run_cuff_segmentation(
            case_data=self.case_data,
            params=params,
            log_callback=self.append_log,
        )

        self.viewer_panel.show_algorithm_result(
            "cuff_result",
            result,
            display_type=self.case_data.get("cuff_display_type", "reference_boundary")
        )
        self.append_log("[完成] 袖口识别/边界定位完成: {}".format(result))
        self.set_status("袖口识别/边界定位完成")

    # =========================
    # 功能流程：基台形态生成
    # =========================
    @Slot()
    def run_abutment_design(self):
        validation_error = self.workflow.validate_before_design(self.case_data)
        if validation_error:
            QMessageBox.warning(self, "流程未完成", validation_error)
            return

        params = self.control_panel.get_abutment_design_params()
        self.append_log("[处理] 开始执行个性化基台形态生成...")
        self.append_log(f"[参数] 基台设计参数: {params}")
        self.set_status("正在执行个性化基台形态生成")

        result = self.workflow.run_abutment_design(
            case_data=self.case_data,
            params=params,
            log_callback=self.append_log,
        )

        self.viewer_panel.show_algorithm_result("abutment_result", result)
        self.append_log(f"[完成] 个性化基台形态生成完成: {result}")
        self.set_status("个性化基台形态生成完成")

    # =========================
    # 结果导出
    # =========================
    @Slot()
    def export_result_model(self):
        has_any_result = any([
            self.case_data.get("match_result"),
            self.case_data.get("cuff_result"),
            self.case_data.get("abutment_result"),
        ])

        if not has_any_result:
            QMessageBox.information(self, "暂无结果", "当前没有可导出的结果。")
            return

        export_root_dir = QFileDialog.getExistingDirectory(
            self,
            "选择结果导出目录",
            str(Path.home())
        )
        if not export_root_dir:
            return

        result = self.workflow.export_results(case_data=self.case_data, export_root_dir=export_root_dir)

        if result.get("success"):
            self.append_log("[导出] 结果已导出到目录: {}".format(result["export_dir"]))
            self.append_log("[导出] 导出模块: {}".format(result["exported_modules"]))
            self.append_log("[导出] 导出文件数: {}".format(result["exported_file_count"]))

            warnings = result.get("warnings", [])
            for warning in warnings:
                self.append_log("[导出][提示] {}".format(warning))

            self.set_status("结果导出完成")
            QMessageBox.information(
                self,
                "导出完成",
                "结果已导出到：\n{}".format(result["export_dir"])
            )
        else:
            self.append_log("[错误] 结果导出失败")
            self.set_status("结果导出失败")
            QMessageBox.warning(self, "导出失败", "结果导出失败。")

    # =========================
    # 显示 / 隐藏
    # =========================
    @Slot()
    def toggle_model_visibility(self, key: str):
        current_visible = self.viewer_panel.model_visibility.get(key, True)
        new_visible = not current_visible

        self.viewer_panel.set_model_visibility(key, new_visible)
        self.data_panel.set_visibility_state(key, new_visible)

        self.append_log("[显示] 切换模型显示状态: {} -> {}".format(
            key, "显示" if new_visible else "隐藏"
        ))

    # =========================
    # 辅助
    # =========================
    @Slot()
    def show_about_dialog(self):
        QMessageBox.about(
            self,
            "关于系统",
            "个性化基台智能设计系统原型\n\n"
            "技术路线：扫描杆匹配与位姿确定 → 牙龈袖口区域识别与边界定位 → "
            "个性化基台穿龈区形态生成 → 结果可视化与导出"
        )

    def append_log(self, message: str):
        self.log_panel.append_log(message)

    def set_status(self, text: str):
        self.status_label.setText(text)

    @Slot(str)
    def on_cuff_display_type_changed(self, display_type: str):
        self.case_data["cuff_display_type"] = display_type
        self.append_log("[显示] 袖口边界显示类型切换为: {}".format(display_type))

        cuff_result = self.case_data.get("cuff_result")
        if cuff_result and cuff_result.get("status") == "success":
            self.viewer_panel.update_cuff_result_display(cuff_result, display_type)
            self.set_status("已切换袖口边界显示类型")
