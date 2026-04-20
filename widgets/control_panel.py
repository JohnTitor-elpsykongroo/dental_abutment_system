# widgets/control_panel.py
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QGroupBox,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QTabWidget,
    QComboBox,
    QHBoxLayout,
)


class ControlPanel(QWidget):
    """
    右侧参数设置区
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(8)

        self.tab_widget = QTabWidget()

        self.tab_widget.addTab(self._build_scanbody_tab(), "扫描杆匹配")
        self.tab_widget.addTab(self._build_cuff_tab(), "袖口识别")
        self.tab_widget.addTab(self._build_design_tab(), "基台生成")

        root_layout.addWidget(self.tab_widget)

    # ============================================================
    # 扫描杆匹配参数
    # ============================================================
    def _build_scanbody_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("扫描杆自动匹配参数")
        form = QFormLayout(group)

        self.match_voxel_size = QDoubleSpinBox()
        self.match_voxel_size.setRange(0.01, 5.0)
        self.match_voxel_size.setDecimals(3)
        self.match_voxel_size.setValue(0.30)

        self.match_ransac_iter = QSpinBox()
        self.match_ransac_iter.setRange(100, 1000000)
        self.match_ransac_iter.setValue(4000)

        self.match_distance_thresh = QDoubleSpinBox()
        self.match_distance_thresh.setRange(0.01, 10.0)
        self.match_distance_thresh.setDecimals(3)
        self.match_distance_thresh.setValue(1.50)

        self.match_enable_refine = QCheckBox("启用精配准")
        self.match_enable_refine.setChecked(True)

        form.addRow("体素下采样尺寸", self.match_voxel_size)
        form.addRow("粗配准迭代次数", self.match_ransac_iter)
        form.addRow("对应距离阈值", self.match_distance_thresh)
        form.addRow("", self.match_enable_refine)

        layout.addWidget(group)
        layout.addStretch(1)
        return widget

    # ============================================================
    # 袖口识别 / 边界重建参数
    # ============================================================
    def _build_cuff_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        group = QGroupBox("袖口边缘提取与参考边界重建参数")
        form = QFormLayout(group)

        self.cuff_loop_select_mode = QComboBox()
        self.cuff_loop_select_mode.addItems(["longest", "manual"])
        self.cuff_loop_select_mode.setCurrentText("longest")

        self.cuff_target_loop_id = QSpinBox()
        self.cuff_target_loop_id.setRange(0, 100)
        self.cuff_target_loop_id.setValue(0)
        self.cuff_target_loop_id.setEnabled(False)

        self.cuff_reference_num_samples = QSpinBox()
        self.cuff_reference_num_samples.setRange(20, 5000)
        self.cuff_reference_num_samples.setValue(240)

        self.cuff_reference_smooth_factor = QDoubleSpinBox()
        self.cuff_reference_smooth_factor.setRange(0.0, 10.0)
        self.cuff_reference_smooth_factor.setDecimals(3)
        self.cuff_reference_smooth_factor.setValue(0.6)

        self.cuff_reference_spline_degree = QSpinBox()
        self.cuff_reference_spline_degree.setRange(1, 5)
        self.cuff_reference_spline_degree.setValue(3)

        self.cuff_display_offset = QDoubleSpinBox()
        self.cuff_display_offset.setRange(0.0, 5.0)
        self.cuff_display_offset.setDecimals(3)
        self.cuff_display_offset.setValue(0.05)

        # 新增：界面显示结果类型
        self.cuff_display_result_type = QComboBox()
        self.cuff_display_result_type.addItems([
            "reference_boundary",
            "raw_boundary",
        ])
        self.cuff_display_result_type.setCurrentText("reference_boundary")

        self.cuff_save_outputs = QCheckBox("保存边界点与参考边界文件")
        self.cuff_save_outputs.setChecked(True)

        form.addRow("边界环选择方式", self.cuff_loop_select_mode)
        form.addRow("手动边界环编号", self.cuff_target_loop_id)
        form.addRow("参考边界采样点数", self.cuff_reference_num_samples)
        form.addRow("平滑因子", self.cuff_reference_smooth_factor)
        form.addRow("样条阶数", self.cuff_reference_spline_degree)
        form.addRow("显示抬升偏移", self.cuff_display_offset)
        form.addRow("界面显示结果", self.cuff_display_result_type)
        form.addRow("", self.cuff_save_outputs)

        layout.addWidget(group)
        layout.addStretch(1)

        self.cuff_loop_select_mode.currentTextChanged.connect(self._on_cuff_mode_changed)

        return widget

    def _on_cuff_mode_changed(self, text: str):
        self.cuff_target_loop_id.setEnabled(text == "manual")

    # ============================================================
    # 基台生成参数
    # ============================================================
    def _build_design_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # ---------- 基础形变参数 ----------
        group_basic = QGroupBox("个性化基台形态生成参数")
        form_basic = QFormLayout(group_basic)

        self.design_emergence_height = QDoubleSpinBox()
        self.design_emergence_height.setRange(0.0, 10.0)
        self.design_emergence_height.setDecimals(3)
        self.design_emergence_height.setValue(1.00)

        self.design_pressure_offset = QDoubleSpinBox()
        self.design_pressure_offset.setRange(-2.0, 5.0)
        self.design_pressure_offset.setDecimals(3)
        self.design_pressure_offset.setValue(0.30)

        self.design_smooth_weight = QDoubleSpinBox()
        self.design_smooth_weight.setRange(0.0, 100.0)
        self.design_smooth_weight.setDecimals(3)
        self.design_smooth_weight.setValue(10.0)
        self.design_smooth_weight.setEnabled(False)  # 当前算法未实际使用，先保留展示

        self.design_export_intermediate = QCheckBox("导出中间结果")
        self.design_export_intermediate.setChecked(True)

        form_basic.addRow("穿龈高度", self.design_emergence_height)
        form_basic.addRow("穿龈压迫量", self.design_pressure_offset)
        form_basic.addRow("平滑约束权重", self.design_smooth_weight)
        form_basic.addRow("", self.design_export_intermediate)

        # ---------- 控制线自动构造参数 ----------
        group_control = QGroupBox("控制区域与控制线构造参数")
        form_control = QFormLayout(group_control)

        self.design_outer_radius_tol = QDoubleSpinBox()
        self.design_outer_radius_tol.setRange(0.0001, 10.0)
        self.design_outer_radius_tol.setDecimals(4)
        self.design_outer_radius_tol.setValue(0.01)

        self.design_outer_z_tol = QDoubleSpinBox()
        self.design_outer_z_tol.setRange(0.0001, 10.0)
        self.design_outer_z_tol.setDecimals(4)
        self.design_outer_z_tol.setValue(0.01)

        self.design_epsilon = QDoubleSpinBox()
        self.design_epsilon.setRange(1e-8, 1e-2)
        self.design_epsilon.setDecimals(8)
        self.design_epsilon.setSingleStep(1e-6)
        self.design_epsilon.setValue(1e-6)

        form_control.addRow("外圈半径阈值", self.design_outer_radius_tol)
        form_control.addRow("上下圈 Z 阈值", self.design_outer_z_tol)
        form_control.addRow("数值稳定项", self.design_epsilon)

        # ---------- 中心点参数 ----------
        group_center = QGroupBox("极角参考中心点")
        center_layout = QHBoxLayout(group_center)

        self.design_center_x = QDoubleSpinBox()
        self.design_center_y = QDoubleSpinBox()
        self.design_center_z = QDoubleSpinBox()

        for spin in [self.design_center_x, self.design_center_y, self.design_center_z]:
            spin.setRange(-1000.0, 1000.0)
            spin.setDecimals(4)
            spin.setValue(0.0)

        center_layout.addWidget(self.design_center_x)
        center_layout.addWidget(self.design_center_y)
        center_layout.addWidget(self.design_center_z)

        layout.addWidget(group_basic)
        layout.addWidget(group_control)
        layout.addWidget(group_center)
        layout.addStretch(1)

        return widget

    # ============================================================
    # 参数读取接口
    # ============================================================
    def get_scanbody_match_params(self):
        return {
            "voxel_size": self.match_voxel_size.value(),
            "ransac_iterations": self.match_ransac_iter.value(),
            "distance_threshold": self.match_distance_thresh.value(),
            "enable_refine": self.match_enable_refine.isChecked(),
        }

    def get_cuff_params(self):
        return {
            "loop_select_mode": self.cuff_loop_select_mode.currentText(),
            "target_loop_id": self.cuff_target_loop_id.value(),
            "reference_num_samples": self.cuff_reference_num_samples.value(),
            "reference_smooth_factor": self.cuff_reference_smooth_factor.value(),
            "reference_spline_degree": self.cuff_reference_spline_degree.value(),
            "display_offset_on_gingiva": self.cuff_display_offset.value(),
            "save_outputs": self.cuff_save_outputs.isChecked(),
        }

    def get_abutment_design_params(self):
        return {
            "emergence_height": self.design_emergence_height.value(),
            "pressure_offset": self.design_pressure_offset.value(),
            "smooth_weight": self.design_smooth_weight.value(),
            "export_intermediate": self.design_export_intermediate.isChecked(),

            "outer_radius_tol": self.design_outer_radius_tol.value(),
            "outer_z_tol": self.design_outer_z_tol.value(),
            "epsilon": self.design_epsilon.value(),
            "center_point": [
                self.design_center_x.value(),
                self.design_center_y.value(),
                self.design_center_z.value(),
            ],
        }